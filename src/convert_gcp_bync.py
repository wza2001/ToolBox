#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多源 GCP 批量投影转换与大地水准面（NetCDF .nc / GeoTIFF）高程改正工具
支持：
  1. 批量遍历 CSV/TSV 文件并清洗合并（自动兼容 GBK/UTF-8 编码）
  2. 读取 GMT surface 导出的 NetCDF (.nc) 网格或 GeoTIFF
  3. 双线性内插高程异常 N，计算正高 H = h - N
  4. 支持 CLI 参数动态切换使用 UTM 投影坐标 (East/North) 或 WGS84 经纬度 (Lon/Lat)
  5. 导出大疆智图（DJI Terra）格式与完整核验报告
"""

import os
import sys
import glob
import pathlib
import argparse
import pandas as pd
import numpy as np
from osgeo import gdal, osr

# 启用 GDAL 异常捕获与 UTF-8 路径支持
gdal.UseExceptions()
gdal.SetConfigOption('GDAL_FILENAME_IS_UTF8', 'YES')

# 字段别名映射库
COL_MAPPING = {
    "id": ["id", "point_name", "pointname", "point", "name", "点名"],
    "lon": ["longitude", "lon", "long", "经度", "x", "east", "easting", "东坐标"],
    "lat": ["latitude", "lat", "纬度", "y", "north", "northing", "北坐标"],
    "alt": ["altitude", "alt", "height", "ellipsoidal_height", "h", "椭球高", "z", "高程"]
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="GCP 坐标转换与大地水准面高程改正工具 (支持 UTM / WGS84 CLI 切换)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-s", "--source",
        dest="source",
        type=str,
        default=r"G:\我的云端硬盘\freedo\Private Work Folder\Projects\Abu_Dhabi_POP\BM_CP\BM_CP.csv",
        help="待处理 GCP 数据文件路径、通配符或目录"
    )
    parser.add_argument(
        "-g", "--geoid",
        dest="geoid_file",
        type=str,
        default=r"D:\WorkStation\ToolBox\data\geoid_surface.nc",
        help="GMT 生成的水准面网格文件路径 (.nc 或 .tif)"
    )
    parser.add_argument(
        "-m", "--coord-mode",
        dest="coord_mode",
        choices=["utm", "wgs84"],
        default="utm",
        help="DJI 格式导出坐标模式: 'utm' (平面东/北坐标) 或 'wgs84' (大地经纬度)"
    )
    parser.add_argument(
        "--epsg",
        dest="epsg",
        type=int,
        default=32640,
        help="目标投影坐标系 EPSG 代码 (默认 32640, 即 WGS84 / UTM Zone 40N)"
    )
    parser.add_argument(
        "-o", "--out-dji",
        dest="out_dji",
        type=str,
        default=r"D:\WorkStation\ToolBox\data\gcp_main_sayydite_dji.csv",
        help="DJI Terra 控制点文件导出路径"
    )
    parser.add_argument(
        "-r", "--out-report",
        dest="out_report",
        type=str,
        default=r"D:\WorkStation\ToolBox\data\gcp_merged_full_report.csv",
        help="完整计算与核验报告导出路径"
    )
    return parser.parse_args()


# ==================== 1. NetCDF / 格网读取与内插引擎 ====================
def load_geoid_grid(grid_path: str):
    """自适应读取 GMT 生成的 NetCDF (.nc) 或 GeoTIFF 网格"""
    if not os.path.exists(grid_path):
        raise FileNotFoundError(f"未找到水准面格网文件: {grid_path}")

    ds = gdal.Open(grid_path)

    if ds.RasterCount == 0:
        subdatasets = ds.GetSubDatasets()
        target_sds = None
        for sds_name, sds_desc in subdatasets:
            if sds_name.endswith(':z') or ':z' in sds_name.lower():
                target_sds = sds_name
                break
        if not target_sds and subdatasets:
            target_sds = subdatasets[0][0]

        print(f"--> 从 NetCDF 中挂载高程异常子数据集: {target_sds}")
        ds = gdal.Open(target_sds)

    gt = ds.GetGeoTransform()
    band = ds.GetRasterBand(1)
    geoid_array = band.ReadAsArray().astype(np.float64)
    x_size, y_size = ds.RasterXSize, ds.RasterYSize

    print(f"--> 水准面格网载入成功: 尺寸={x_size}×{y_size}, 像元步长=[Lon: {gt[1]:.7f}°, Lat: {abs(gt[5]):.7f}°]")
    return geoid_array, gt, x_size, y_size


def sample_geoid(lon: float, lat: float, geoid_array: np.ndarray, gt: tuple, x_size: int, y_size: int) -> float:
    """双线性内插提取大地水准面差距 N"""
    px = (lon - gt[0]) / gt[1]
    py = (lat - gt[3]) / gt[5]

    x0 = int(np.floor(px))
    y0 = int(np.floor(py))

    if 0 <= x0 < x_size - 1 and 0 <= y0 < y_size - 1:
        dx = px - x0
        dy = py - y0
        # 修复后的双线性内插计算
        n = (geoid_array[y0, x0] * (1.0 - dx) * (1.0 - dy) +
             geoid_array[y0, x0 + 1] * dx * (1.0 - dy) +
             geoid_array[y0 + 1, x0] * (1.0 - dx) * dy +
             geoid_array[y0 + 1, x0 + 1] * dx * dy)
        return float(n)
    else:
        # 边界外推兜底（最近邻）
        x_clp = int(np.clip(round(px), 0, x_size - 1))
        y_clp = int(np.clip(round(py), 0, y_size - 1))
        return float(geoid_array[y_clp, x_clp])


# ==================== 2. 批量读取与多源文件合并 ====================
def find_matched_col(df_columns, candidates):
    """从表格列名中智能匹配标准字段"""
    col_lookup = {str(c).strip().lower(): c for c in df_columns}
    for cand in candidates:
        if cand.lower() in col_lookup:
            return col_lookup[cand.lower()]
    return None


def collect_csv_files(source_path: str) -> list:
    """检索所有待合并的 CSV/TSV 文件"""
    p = pathlib.Path(source_path)
    if p.is_dir():
        files = list(p.glob("*.csv")) + list(p.glob("*.tsv")) + list(p.glob("*.txt"))
    elif "*" in source_path:
        files = [pathlib.Path(f) for f in glob.glob(source_path)]
    elif p.is_file():
        files = [p]
    else:
        raise FileNotFoundError(f"找不到指定的路径或文件: {source_path}")
    return sorted(files)


def batch_load_gcps(file_list: list) -> pd.DataFrame:
    """循环读取各个文件并统一字段结构（内置编码容错）"""
    dfs = []
    print(f"\n[开始扫描文件] 发现 {len(file_list)} 个待处理数据文件：")

    # 常见编码轮询列表
    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb18030', 'latin1']

    for fpath in file_list:
        df_sub = None
        for enc in encodings:
            try:
                df_sub = pd.read_csv(fpath, sep=None, engine='python', encoding=enc)
                break
            except (UnicodeDecodeError, Exception):
                continue

        if df_sub is None:
            print(f"  [读取失败] {fpath.name}: 无法使用常见编码识别，请检查文件格式。")
            continue

        try:
            df_sub.columns = df_sub.columns.astype(str).str.strip()

            id_col = find_matched_col(df_sub.columns, COL_MAPPING["id"])
            lon_col = find_matched_col(df_sub.columns, COL_MAPPING["lon"])
            lat_col = find_matched_col(df_sub.columns, COL_MAPPING["lat"])
            alt_col = find_matched_col(df_sub.columns, COL_MAPPING["alt"])

            if not all([id_col, lon_col, lat_col, alt_col]):
                print(f"  [跳过] {fpath.name}: 关键列缺失 (检测到: {list(df_sub.columns)})")
                continue

            df_sub = df_sub.rename(columns={
                id_col: "PointName",
                lon_col: "Raw_X",
                lat_col: "Raw_Y",
                alt_col: "Ellipsoidal_h"
            })

            df_sub["Source_File"] = fpath.name
            dfs.append(df_sub)
            print(f"  [已载入] {fpath.name:<30} ({len(df_sub)} 个点)")

        except Exception as e:
            print(f"  [解析失败] {fpath.name}: {e}")

    if not dfs:
        raise ValueError("未能成功解析出任何有效控制点数据，请检查文件内容。")

    merged_df = pd.concat(dfs, ignore_index=True)
    print(f"--> 合并完成，共收集 {len(merged_df)} 条 GCP 数据。")
    return merged_df


# ==================== 3. 主执行流水线 ====================
def main():
    args = parse_args()

    # 3.1 加载水准面格网 (.nc)
    geoid_array, gt, x_size, y_size = load_geoid_grid(args.geoid_file)

    # 3.2 批量读取控制点表格
    files = collect_csv_files(args.source)
    df = batch_load_gcps(files)

    # 3.3 初始化坐标转换器
    # WGS84 经纬度 (EPSG:4326)
    wgs84_srs = osr.SpatialReference()
    wgs84_srs.ImportFromEPSG(4326)
    wgs84_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    # 目标 UTM 投影系
    utm_srs = osr.SpatialReference()
    utm_srs.ImportFromEPSG(args.epsg)
    utm_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    wgs84_to_utm = osr.CoordinateTransformation(wgs84_srs, utm_srs)
    utm_to_wgs84 = osr.CoordinateTransformation(utm_srs, wgs84_srs)

    # 3.4 智能判断输入坐标类型并进行双向补全
    first_x = float(df.iloc[0]["Raw_X"])
    first_y = float(df.iloc[0]["Raw_Y"])
    input_is_utm = (abs(first_x) > 180.0 or abs(first_y) > 90.0)

    if input_is_utm:
        print(f"--> 检测到输入数据为 [UTM 投影米制坐标] (X: {first_x:.2f}, Y: {first_y:.2f})")
    else:
        print(f"--> 检测到输入数据为 [WGS84 经纬度度制坐标] (Lon: {first_x:.6f}°, Lat: {first_y:.6f}°)")

    lons, lats = [], []
    eastings, northings = [], []
    geoid_ns, ortho_hs = [], []

    for _, row in df.iterrows():
        raw_x = float(row["Raw_X"])
        raw_y = float(row["Raw_Y"])
        h = float(row["Ellipsoidal_h"])

        if input_is_utm:
            # 输入是 UTM -> 逆投影算出 Lon/Lat 供格网采样
            lon, lat, _ = utm_to_wgs84.TransformPoint(raw_x, raw_y)
            e, n = raw_x, raw_y
        else:
            # 输入是 Lon/Lat -> 正投影算出 UTM East/North
            lon, lat = raw_x, raw_y
            e, n, _ = wgs84_to_utm.TransformPoint(lon, lat)

        lons.append(round(lon, 8))
        lats.append(round(lat, 8))
        eastings.append(round(e, 4))
        northings.append(round(n, 4))

        # 双线性插值求高程异常 N (网格必须用 Lon, Lat 检索)
        n_val = sample_geoid(lon, lat, geoid_array, gt, x_size, y_size)
        geoid_ns.append(round(n_val, 4))

        # 正高 H = 椭球高 h - 高程异常 N
        ortho_h = h - n_val
        ortho_hs.append(round(ortho_h, 4))

    # 统一存入 DataFrame
    df["Longitude"] = lons
    df["Latitude"] = lats
    df["UTM_East"] = eastings
    df["UTM_North"] = northings
    df["Geoid_N"] = geoid_ns
    df["Ortho_Height"] = ortho_hs

    # 3.5 根据 CLI 模式生成大疆智图（DJI Terra）格式
    if args.coord_mode == "utm":
        print(f"\n--> 正在生成大疆智图格式 [UTM 投影平面坐标 (EPSG:{args.epsg})]")
        dji_export = pd.DataFrame({
            "PointName": df["PointName"],
            "X_East": df["UTM_East"],
            "Y_North": df["UTM_North"],
            "Z_Height": df["Ortho_Height"]
        })
    else:
        print("\n--> 正在生成大疆智图格式 [WGS84 大地经纬度坐标 (EPSG:4326)]")
        dji_export = pd.DataFrame({
            "PointName": df["PointName"],
            "Longitude": df["Longitude"],
            "Latitude": df["Latitude"],
            "Z_Height": df["Ortho_Height"]
        })

    # 创建输出目录并导出
    os.makedirs(os.path.dirname(os.path.abspath(args.out_dji)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.out_report)), exist_ok=True)

    dji_export.to_csv(args.out_dji, index=False)
    df.to_csv(args.out_report, index=False)

    print("\n" + "=" * 60)
    print("【转换成功】")
    print(f"坐标导出模式       : {args.coord_mode.upper()}")
    print(f"1. 大疆智图直接导入: {os.path.abspath(args.out_dji)}")
    print(f"2. 完整核验报告    : {os.path.abspath(args.out_report)}")
    print("=" * 60)
    print("\n前 5 个点位结果预览：")
    print(dji_export.head().to_string(index=False))


if __name__ == "__main__":
    main()