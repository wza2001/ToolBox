import os
import shutil
import re


def sync_delete_by_template(
        root_dir=".",
        template_folder="A",
        target_folders=("D", "S", "W", "X"),
        backup_mode=True
):
    """
    以 template_folder 为基准，镜像删除 target_folders 中多余的照片。

    :param root_dir: 包含 A, D, S, W, X 的根目录路径
    :param template_folder: 基准文件夹名称（默认 'A'）
    :param target_folders: 需要同步清理的其它镜头文件夹
    :param backup_mode: True 为安全移动到备份文件夹，False 为直接硬删除
    """
    template_path = os.path.join(root_dir, template_folder)

    if not os.path.exists(template_path):
        print(f"[-] 错误：基准文件夹不存在: {template_path}")
        return

    # 1. 获取基准文件夹 A 中所有照片的纯数字/后缀标识
    # 匹配命名规则如 A00005.JPG -> 提取 00005.JPG
    template_suffixes = set()
    for filename in os.listdir(template_path):
        if filename.lower().endswith(('.jpg', '.jpeg', '.tif', '.tiff', '.png')):
            # 去掉开头的文件夹前缀字母（如 A），保留后续编号和扩展名
            suffix = filename[len(template_folder):]
            template_suffixes.add(suffix)

    print(f"[*] 基准文件夹 [{template_folder}] 中共有有效照片: {len(template_suffixes)} 张")

    # 2. 扫描 D, S, W, X 文件夹，找出需要删除的文件列表
    files_to_delete = []  # 元素格式: (原文件完整路径, 相对路径)

    for folder in target_folders:
        folder_path = os.path.join(root_dir, folder)
        if not os.path.exists(folder_path):
            print(f"[!] 警告：未找到文件夹 [{folder}]，已跳过。")
            continue

        for filename in os.listdir(folder_path):
            if filename.lower().endswith(('.jpg', '.jpeg', '.tif', '.tiff', '.png')):
                suffix = filename[len(folder):]
                # 如果这个编号不在基准 A 文件夹中，则加入待删除列表
                if suffix not in template_suffixes:
                    full_path = os.path.join(folder_path, filename)
                    rel_path = os.path.join(folder, filename)
                    files_to_delete.append((full_path, rel_path))

    # 3. 结果汇总与确认
    total_to_delete = len(files_to_delete)
    if total_to_delete == 0:
        print("[✓] 其它文件夹的照片与基准文件夹 [A] 完全一致，无需删除任何文件。")
        return

    print("\n" + "=" * 50)
    print(f"共检测到 {total_to_delete} 张需要同步删除的多余照片：")
    print("=" * 50)
    # 打印前 10 个示例，避免刷屏
    for _, rel_path in files_to_delete[:10]:
        print(f" - {rel_path}")
    if total_to_delete > 10:
        print(f"   ... 以及其余 {total_to_delete - 10} 张照片")
    print("=" * 50)

    # 4. 用户交互确认
    action_name = "移动到备份文件夹" if backup_mode else "永久删除"
    confirm = input(f"\n[?] 确认将以上 {total_to_delete} 张照片【{action_name}】吗？(y/n): ").strip().lower()

    if confirm != 'y':
        print("[-] 操作已取消，未对任何文件进行修改。")
        return

    # 5. 执行操作
    backup_dir = os.path.join(root_dir, "_Deleted_Backup")
    success_count = 0

    for full_path, rel_path in files_to_delete:
        try:
            if backup_mode:
                # 保持原目录层级结构移动到备份文件夹中，例如 _Deleted_Backup/D/D00001.JPG
                dest_path = os.path.join(backup_dir, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.move(full_path, dest_path)
            else:
                os.remove(full_path)
            success_count += 1
        except Exception as e:
            print(f"[✗] 处理失败 {rel_path}: {e}")

    print("\n" + "=" * 50)
    if backup_mode:
        print(f"[✓] 处理完成！已成功将 {success_count} 张照片移动至: {backup_dir}")
    else:
        print(f"[✓] 处理完成！已成功删除 {success_count} 张照片。")
    print("=" * 50)


if __name__ == '__main__':
    # 配置航测照片根目录：
    # 如果脚本放在包含 A, D, S, W, X 文件夹的同一目录下，保持 "." 即可
    ROOT_DIRECTORY = r"K:\8_31_1\20260831_001-002\ValidData\image\ADSWX_Sight"

    # 是否开启备份模式（推荐开启 True：避免误删；若设为 False 则直接物理删除）
    ENABLE_BACKUP = True

    sync_delete_by_template(
        root_dir=ROOT_DIRECTORY,
        template_folder="A",
        target_folders=["D", "S", "W", "X"],
        backup_mode=ENABLE_BACKUP
    )