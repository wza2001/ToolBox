import sys
import argparse
import pandas as pd
import math
from pathlib import Path
from datetime import datetime
import shutil
from geopy.distance import geodesic
from tqdm import tqdm
from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS
from pillow_heif import register_heif_opener

# Enable HEIC support in Pillow
register_heif_opener()

def parse_args():
    parser = argparse.ArgumentParser(description="GCP-Photo Matching Tool")
    # Restore original argument names for backwards compatibility, but keep shorthand options
    parser.add_argument("-e", "--excel_dir", dest="excel_dir", type=str, required=True, help="Path to the folder containing GCP Excel files (.xlsx, .xls).")
    parser.add_argument("-p", "--photo_dir", dest="photo_dir", type=str, required=True, help="Path to the folder containing aerial/ground photos.")
    parser.add_argument("-o", "--output_dir", dest="output_dir", type=str, default="./GCP_Photo_Output", help="Path where organized folders and reports will be saved.")
    parser.add_argument("-b", "--buffer_distance", dest="buffer_distance", type=float, default=50.0, help="Buffer radius in meters for spatial matching (default: 50.0).")
    parser.add_argument("-t", "--time-window", dest="time_window", type=int, default=300, help="Maximum allowed time difference in seconds between photo and GCP timestamp.")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Run the spatial analysis without copying or modifying files.")
    parser.add_argument("--copy-mode", dest="copy_mode", choices=['copy', 'move'], default='copy', help="Choose whether to duplicate photos into GCP folders or move them.")
    parser.add_argument("--force", action="store_true", help="Suppress interactive warning if output_dir already exists.")
    return parser.parse_args()

def parse_datetime(val):
    if pd.isna(val):
        return None

    if isinstance(val, pd.Timestamp):
        dt = val.to_pydatetime()
    elif isinstance(val, datetime):
        dt = val
    else:
        try:
            # 自动解析 ISO 8601 格式（包含 'Z' 或时区偏移）
            ts = pd.to_datetime(val)
            if ts.tzinfo is not None:
                # 转为阿布扎比当地时区 UTC+4 (Asia/Dubai) 并剥离时区属性
                dt = ts.tz_convert('Asia/Dubai').tz_localize(None).to_pydatetime()
            else:
                dt = ts.to_pydatetime()
        except Exception:
            return None

    if dt and dt.tzinfo:
        dt = dt.replace(tzinfo=None)

    return dt

def dms_to_decimal(val, ref):
    if not val or not ref:
        return None
    try:
        d, m, s = val

        # PIL IFDRational handling
        d = float(d) if hasattr(d, 'real') else float(d[0]) / float(d[1])
        m = float(m) if hasattr(m, 'real') else float(m[0]) / float(m[1])
        s = float(s) if hasattr(s, 'real') else float(s[0]) / float(s[1])

        decimal = d + (m / 60.0) + (s / 3600.0)
        if ref in ['S', 'W']:
            decimal = -decimal
        return decimal
    except Exception:
        return None

def get_photo_datetime(image_path):
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if not exif:
                return None

            # Read DateTimeOriginal (tag 36867) from the Exif SubIFD
            dt_str = None
            try:
                sub_ifd = exif.get_ifd(0x8769)
                if sub_ifd and 36867 in sub_ifd:
                    dt_str = sub_ifd[36867]
            except Exception:
                pass

            # Fall back to root tags 36867 or 306
            if not dt_str:
                dt_str = exif.get(36867) or exif.get(306)

            if not dt_str:
                return None

            # EXIF format is usually "YYYY:MM:DD HH:MM:SS"
            dt_str = str(dt_str).strip()
            try:
                return datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
            except ValueError:
                # Try parsing as standard ISO string if the usual format fails
                try:
                    dt = pd.to_datetime(dt_str.replace(':', '-', 2)).to_pydatetime()
                    if dt.tzinfo:
                        dt = dt.replace(tzinfo=None)
                    return dt
                except Exception:
                    return None
    except Exception:
        pass
    return None

def get_gps_from_exif(image_path):
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if not exif:
                return None, None

            gps_info = exif.get_ifd(0x8825) # 0x8825 is the GPS IFD

            if not gps_info:
                return None, None

            gps_tags = {}
            for tag, value in gps_info.items():
                decoded = GPSTAGS.get(tag, tag)
                gps_tags[decoded] = value

            lat = dms_to_decimal(gps_tags.get('GPSLatitude'), gps_tags.get('GPSLatitudeRef'))
            lon = dms_to_decimal(gps_tags.get('GPSLongitude'), gps_tags.get('GPSLongitudeRef'))

            if lat is not None and lon is not None:
                return lat, lon
    except Exception:
        pass
    return None, None

def process_excel_files(excel_files):
    df_list = []

    # Progress Bar 1: Reading and deduplicating Excel files
    for f in tqdm(excel_files, desc="Reading Excel/CSV Files"):
        try:
            if f.suffix.lower() == '.csv':
                # Try different encodings for CSV
                success = False
                for enc in ['utf-8-sig', 'gbk', 'latin1']:
                    try:
                        df = pd.read_csv(f, encoding=enc)
                        success = True
                        break
                    except UnicodeDecodeError:
                        continue
                if not success:
                    print(f"Failed to read {f}: Unknown encoding")
                    continue
            else:
                df = pd.read_excel(f)
            df_list.append(df)
        except Exception as e:
            print(f"Failed to read {f}: {e}")

    if not df_list:
        raise ValueError("Could not read any Excel files.")

    merged_df = pd.concat(df_list, ignore_index=True)

    # Check for required columns and standardize casing
    required_cols_map = {
        'point_name': ['point_name', 'pointname', 'name', 'point'],
        'latitude': ['latitude', 'lat'],
        'longitude': ['longitude', 'lon', 'long']
    }

    for req_col, aliases in required_cols_map.items():
        if req_col not in merged_df.columns:
            # Try to find a matching column
            matched = False
            for col in merged_df.columns:
                if str(col).lower() in aliases:
                    merged_df.rename(columns={col: req_col}, inplace=True)
                    matched = True
                    break
            if not matched:
                raise ValueError(f"Missing required column: {req_col}. Found columns: {list(merged_df.columns)}")

    # Optional columns standardizing (just making sure they exist, if not create empty)
    core_cols = ['ID', 'point_name', 'latitude', 'longitude', 'altitude', 'north', 'east', 'Recorded at']

    # Deduplicate
    pre_dedup_count = len(merged_df)
    merged_df = merged_df.drop_duplicates(subset=['point_name', 'latitude', 'longitude'])
    post_dedup_count = len(merged_df)

    # Add ID
    merged_df.insert(0, 'ID', range(1, len(merged_df) + 1))

    # Retain core attributes, filling missing ones with None
    for col in core_cols:
        if col not in merged_df.columns:
            merged_df[col] = None

    merged_df = merged_df[core_cols].copy()

    # Parse the 'Recorded at' column into standard Python datetime (naive)
    if 'Recorded at' in merged_df.columns:
        merged_df['Recorded at'] = merged_df['Recorded at'].apply(parse_datetime)

    # Initialize tracking columns
    merged_df['PhotoCheck_Or_Not'] = 'No'
    merged_df['Matched_Photos'] = ''

    return merged_df, pre_dedup_count, post_dedup_count

def check_preflight(excel_dir, photo_dir, output_dir, force):
    # 1. Verify directories exist
    if not excel_dir.exists() or not excel_dir.is_dir():
        print(f"Error: Excel directory '{excel_dir}' does not exist or is not a directory.")
        sys.exit(1)
    if not photo_dir.exists() or not photo_dir.is_dir():
        print(f"Error: Photo directory '{photo_dir}' does not exist or is not a directory.")
        sys.exit(1)

    # 2. Check for Excel/CSV files
    excel_files = [
        f for f in list(excel_dir.glob("*.xlsx")) + list(excel_dir.glob("*.xls")) + list(excel_dir.glob("*.csv"))
        if not f.name.startswith("~$")
    ]

    if not excel_files:
        print(f"Error: No valid Excel/CSV files (.xlsx, .xls, .csv) found in '{excel_dir}'.")
        sys.exit(1)

    # 3. Check for valid image files
    photo_extensions = {".jpg", ".jpeg", ".heic", ".heif"}
    photos = [p for p in photo_dir.rglob("*") if p.is_file() and p.suffix.lower() in photo_extensions]
    if not photos:
        print(f"Error: No valid image files (.jpg, .jpeg, .heic, .heif) found in '{photo_dir}'.")
        sys.exit(1)

    # 4. Prompt if output_dir exists and is non-empty
    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        # Check if we're connected to a terminal to avoid hanging automated scripts
        if sys.stdin.isatty():
            response = input(f"Warning: Output directory '{output_dir}' already exists and is non-empty.\nDo you want to overwrite/append? [y/N]: ")
            if response.lower() not in ['y', 'yes']:
                print("Operation aborted by user.")
                sys.exit(0)
        else:
            print(f"Error: Output directory '{output_dir}' already exists and is non-empty. Use --force to overwrite in automated environments.")
            sys.exit(1)

    return excel_files, photos

def print_banner(args):
    banner = f"""
============================================================
              GCP-Photo Matching Tool CLI
============================================================
Configuration:
  Excel Directory : {args.excel_dir}
  Photo Directory : {args.photo_dir}
  Output Directory: {args.output_dir}
  Buffer Distance : {args.buffer_distance} meters
  Time Window     : {args.time_window} seconds
  Copy Mode       : {args.copy_mode}
  Dry Run         : {'Yes' if args.dry_run else 'No'}
============================================================
"""
    print(banner)

def main():
    args = parse_args()
    print_banner(args)

    excel_dir = Path(args.excel_dir)
    photo_dir = Path(args.photo_dir)
    output_dir = Path(args.output_dir)

    excel_files, photos = check_preflight(excel_dir, photo_dir, output_dir, args.force)

    unmatched_dir = output_dir / "Inconnect_photo"
    no_gps_dir = unmatched_dir / "No_GPS"
    manual_calibration_dir = output_dir / "Manual_Calibration"

    gcp_df, pre_dedup_count, post_dedup_count = process_excel_files(excel_files)
    dedup_removed = pre_dedup_count - post_dedup_count

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        unmatched_dir.mkdir(parents=True, exist_ok=True)
        no_gps_dir.mkdir(parents=True, exist_ok=True)
        manual_calibration_dir.mkdir(parents=True, exist_ok=True)

        # 1. Strict Folder Scaffolding
        for idx, row in gcp_df.iterrows():
            gcp_id = row['ID']
            gcp_folder = output_dir / f"GCP_{gcp_id}"
            gcp_folder.mkdir(parents=True, exist_ok=True)

    total_photos = len(photos)
    status_counts = {
        "NO_GPS": 0,
        "UNMATCHED": 0,
        "HIGH": 0,
        "SPATIAL_ONLY": 0,
        "TEMPORAL_ONLY": 0,
        "CONFLICT": 0
    }

    matched_dict = {row['ID']: [] for _, row in gcp_df.iterrows()}
    conflict_dict = {row['ID']: [] for _, row in gcp_df.iterrows()}
    match_basis_dict = {row['ID']: [] for _, row in gcp_df.iterrows()}

    copy_queue = [] # list of tuples: (source_path, dest_path)

    for photo_path in tqdm(photos, desc="Evaluating Photos"):
        lat, lon = get_gps_from_exif(photo_path)
        photo_time = get_photo_datetime(photo_path)

        has_gps = lat is not None and lon is not None

        candidates = []

        # Find candidates (OR logic)
        for idx, row in gcp_df.iterrows():
            gcp_lat = row['latitude']
            gcp_lon = row['longitude']
            gcp_time = row['Recorded at']

            spatial_match = False
            temporal_match = False

            if has_gps and not pd.isna(gcp_lat) and not pd.isna(gcp_lon):
                try:
                    gcp_lat = float(gcp_lat)
                    gcp_lon = float(gcp_lon)
                    dist = geodesic((lat, lon), (gcp_lat, gcp_lon)).meters
                    if dist <= args.buffer_distance:
                        spatial_match = True
                except ValueError:
                    pass

            if photo_time is not None and not pd.isna(gcp_time):
                time_diff = abs((photo_time - gcp_time).total_seconds())
                if time_diff <= args.time_window:
                    temporal_match = True

            if spatial_match and temporal_match:
                candidates.append({'row': row, 'tier': 1, 'tier_name': 'HIGH', 'basis': 'Both'})
            elif spatial_match:
                candidates.append({'row': row, 'tier': 2, 'tier_name': 'SPATIAL_ONLY', 'basis': 'Spatial_Only'})
            elif temporal_match:
                candidates.append({'row': row, 'tier': 3, 'tier_name': 'TEMPORAL_ONLY', 'basis': 'Temporal_Only'})

        if not candidates:
            if not has_gps:
                status_counts["NO_GPS"] += 1
                copy_queue.append((photo_path, no_gps_dir / photo_path.name))
            else:
                status_counts["UNMATCHED"] += 1
                copy_queue.append((photo_path, unmatched_dir / photo_path.name))
            continue

        # Arbitration
        # Find best tier
        best_tier = min(c['tier'] for c in candidates)
        best_candidates = [c for c in candidates if c['tier'] == best_tier]

        if len(best_candidates) == 1:
            best = best_candidates[0]
            gcp_id = best['row']['ID']
            tier_name = best['tier_name']
            basis = best['basis']

            matched_dict[gcp_id].append(photo_path.name)
            match_basis_dict[gcp_id].append(f"{photo_path.name} ({basis})")
            status_counts[tier_name] += 1

            gcp_folder = output_dir / f"GCP_{gcp_id}"
            copy_queue.append((photo_path, gcp_folder / photo_path.name))
        else:
            gcp_ids = [c['row']['ID'] for c in best_candidates]
            status_counts["CONFLICT"] += 1
            copy_queue.append((photo_path, manual_calibration_dir / photo_path.name))
            for cid in gcp_ids:
                conflict_dict[cid].append(photo_path.name)

    # File Distribution
    if not args.dry_run:
        for src, dest in tqdm(copy_queue, desc="Copying/Moving Photos"):
            shutil.copy2(src, dest)
            if args.copy_mode == 'move':
                if src.exists():
                    src.unlink()

    # Update DataFrame with results
    matched_gcps_count = 0
    gcp_df['PhotoCheck_Or_Not'] = 'No'
    gcp_df['Matched_Count'] = 0
    gcp_df['Matched_Photos'] = ''
    gcp_df['Conflict_Photos'] = ''
    gcp_df['Match_Basis'] = ''

    for idx, row in gcp_df.iterrows():
        gcp_id = row['ID']
        m_photos = matched_dict[gcp_id]
        c_photos = conflict_dict[gcp_id]
        basis_list = match_basis_dict[gcp_id]

        gcp_df.at[idx, 'Matched_Count'] = len(m_photos)

        if m_photos:
            gcp_df.at[idx, 'Matched_Photos'] = ', '.join(m_photos)
            gcp_df.at[idx, 'Match_Basis'] = ', '.join(basis_list)
            gcp_df.at[idx, 'PhotoCheck_Or_Not'] = 'Yes'
            matched_gcps_count += 1
        elif c_photos:
            gcp_df.at[idx, 'PhotoCheck_Or_Not'] = 'Conflict'

        if c_photos:
            gcp_df.at[idx, 'Conflict_Photos'] = ', '.join(c_photos)

    # Export Report
    today_str = datetime.now().strftime("%Y%m%d")
    report_path = output_dir / f"RawGCP_{today_str}.xlsx"

    if not args.dry_run:
        gcp_df.to_excel(report_path, index=False)

    # Print summary
    points_no_photos = len(gcp_df) - matched_gcps_count

    print("\n" + "="*60)
    print(" SUMMARY REPORT")
    print("="*60)
    print(f"Total GCP Points Loaded         : {pre_dedup_count}")
    print(f"Duplicate Points Removed        : {dedup_removed}")
    print(f"Final GCP Points Processed      : {len(gcp_df)}")
    print("-" * 60)
    print(f"Total Photos Scanned            : {total_photos}")
    print(f"Photos NO_GPS                   : {status_counts['NO_GPS']}")
    print(f"Photos UNMATCHED                : {status_counts['UNMATCHED']}")
    print(f"Photos HIGH (Both Match)        : {status_counts['HIGH']}")
    print(f"Photos SPATIAL_ONLY             : {status_counts['SPATIAL_ONLY']}")
    print(f"Photos TEMPORAL_ONLY            : {status_counts['TEMPORAL_ONLY']}")
    print(f"Photos CONFLICT (>1 Best Tie)   : {status_counts['CONFLICT']}")
    print("-" * 60)
    print(f"Points with Matching Photos     : {matched_gcps_count}")
    print(f"Points with ZERO Photos         : {points_no_photos}")
    print("="*60)
    if args.dry_run:
        print("Dry run enabled. No report exported.")
    else:
        print(f"Report exported to:\n  {report_path.resolve()}")
    print("="*60)

if __name__ == "__main__":
    main()
