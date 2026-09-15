import csv
import os
import piexif

def deg_to_dms_rational(deg_float):
    """
    将十进制度数转换为 EXIF 规范所需的度、分、秒有理数格式 ((度, 1), (分, 1), (秒*10000, 10000))
    """
    deg_float = abs(deg_float)
    deg = int(deg_float)
    min_float = (deg_float - deg) * 60.0
    minute = int(min_float)
    sec_float = (min_float - minute) * 60.0
    sec_int = int(round(sec_float * 10000))
    return ((deg, 1), (minute, 1), (sec_int, 10000))

def update_photo_pos(csv_path, base_dir="."):
    """
    读取 CSV 文件并更新对应照片的 EXIF POS 信息
    :param csv_path: CSV 文件的路径
    :param base_dir: 照片相对路径的根目录（默认为当前目录）
    """
    if not os.path.exists(csv_path):
        print(f"[-] CSV 文件不存在: {csv_path}")
        return

    success_count = 0
    fail_count = 0

    with open(csv_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            # 兼容 Windows/Linux 路径分隔符
            rel_path = row['Name'].strip().replace('\\', os.sep).replace('/', os.sep)
            photo_path = os.path.join(base_dir, rel_path)

            if not os.path.exists(photo_path):
                print(f"[!] 照片未找到: {photo_path}，跳过...")
                fail_count += 1
                continue

            try:
                lat = float(row['Latitude'])
                lon = float(row['Longitude'])
                alt = float(row['Height'])
                yaw = float(row['Yaw'])
                pitch = float(row['Pitch'])
                roll = float(row['Roll'])

                # 读取现有 EXIF 数据（如果没有则新建空字典）
                try:
                    exif_dict = piexif.load(photo_path)
                except Exception:
                    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

                if "GPS" not in exif_dict or not isinstance(exif_dict["GPS"], dict):
                    exif_dict["GPS"] = {}

                # 1. 纬度 Latitude
                exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b'N' if lat >= 0 else b'S'
                exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = deg_to_dms_rational(lat)

                # 2. 经度 Longitude
                exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b'E' if lon >= 0 else b'W'
                exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = deg_to_dms_rational(lon)

                # 3. 高度 Height / Altitude (以毫米或厘米级有理数存储)
                # GPSAltitudeRef: 0 为海平面以上, 1 为海平面以下
                exif_dict["GPS"][piexif.GPSIFD.GPSAltitudeRef] = 0 if alt >= 0 else 1
                exif_dict["GPS"][piexif.GPSIFD.GPSAltitude] = (int(abs(alt) * 1000), 1000)

                # 4. 偏航角/航向角 Yaw (映射到标准 GPS 方向角 GPSImgDirection, 0~360度)
                yaw_normalized = (yaw + 360.0) % 360.0
                exif_dict["GPS"][piexif.GPSIFD.GPSImgDirectionRef] = b'T'  # T = True north (真北)
                exif_dict["GPS"][piexif.GPSIFD.GPSImgDirection] = (int(yaw_normalized * 100), 100)

                # 5. 将 Pitch, Roll, Yaw 姿态角完整记录到 ImageDescription (0th IFD) 便于后续软件解析
                pose_str = f"Pitch:{pitch:.6f};Roll:{roll:.6f};Yaw:{yaw:.6f};Height:{alt:.3f}"
                exif_dict["0th"][piexif.ImageIFD.ImageDescription] = pose_str.encode('utf-8')

                # 将更新后的 EXIF 写回照片文件
                exif_bytes = piexif.dump(exif_dict)
                piexif.insert(exif_bytes, photo_path)

                print(f"[✓] 成功更新: {rel_path} -> Lat: {lat:.6f}, Lon: {lon:.6f}, Alt: {alt:.2f}m")
                success_count += 1

            except Exception as e:
                print(f"[✗] 处理失败 {photo_path}: {e}")
                fail_count += 1

    print("\n" + "="*40)
    print(f"处理完成！成功: {success_count} 张, 失败/未找到: {fail_count} 张")
    print("="*40)


if __name__ == '__main__':
    # CSV 文件路径
    CSV_FILE = "pos_data.csv"
    
    # 照片根目录：如果 CSV 和包含照片文件夹（如 A/）在同一目录下，保持 "." 即可
    # 如果照片在其他文件夹，如 "D:/photos"，请修改此处为 "D:/photos"
    PHOTOS_ROOT_DIR = "."

    update_photo_pos(CSV_FILE, PHOTOS_ROOT_DIR)
