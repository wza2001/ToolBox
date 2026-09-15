import sys
import argparse
import pandas as pd
import math
from pathlib import Path
from datetime import datetime
import shutil
import exifread
from geopy.distance import geodesic
from tqdm import tqdm

def parse_args():
    parser = argparse.ArgumentParser(description="GCP-Photo Matching Tool")
    parser.add_argument("-e", "--excel-dir", dest="excel_dir", type=str, required=True, help="Path to the folder containing GCP Excel files (.xlsx, .xls).")
    parser.add_argument("-p", "--photo-dir", dest="photo_dir", type=str, required=True, help="Path to the folder containing aerial/ground photos.")
    parser.add_argument("-o", "--output-dir", dest="output_dir", type=str, default="./GCP_Photo_Output", help="Path where organized folders and reports will be saved.")
    parser.add_argument("-b", "--buffer", dest="buffer_distance", type=float, default=50.0, help="Buffer radius in meters for spatial matching (default: 50.0).")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Run the spatial analysis without copying or modifying files.")
    parser.add_argument("--copy-mode", dest="copy_mode", choices=['copy', 'move'], default='copy', help="Choose whether to duplicate photos into GCP folders or move them.")
    parser.add_argument("--force", action="store_true", help="Suppress interactive warning if output_dir already exists.")
    return parser.parse_args()

def dms_to_decimal(tags, ref_tag, val_tag):
    if ref_tag not in tags or val_tag not in tags:
        return None
    try:
        ref = tags[ref_tag].values
        val = tags[val_tag].values

        # Guard against zero division
        d = float(val[0].num) / float(val[0].den) if val[0].den != 0 else 0
        m = float(val[1].num) / float(val[1].den) if val[1].den != 0 else 0
        s = float(val[2].num) / float(val[2].den) if val[2].den != 0 else 0

        decimal = d + (m / 60.0) + (s / 3600.0)
        if ref in ['S', 'W']:
            decimal = -decimal
        return decimal
    except Exception:
        return None

def get_gps_from_exif(image_path):
    try:
        with open(image_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)

            lat = dms_to_decimal(tags, 'GPS GPSLatitudeRef', 'GPS GPSLatitude')
            lon = dms_to_decimal(tags, 'GPS GPSLongitudeRef', 'GPS GPSLongitude')

            if lat is not None and lon is not None:
                return lat, lon
    except Exception:
        pass
    return None, None

def process_excel_files(excel_files):
    df_list = []

    # Progress Bar 1: Reading and deduplicating Excel files
    for f in tqdm(excel_files, desc="Reading Excel Files"):
        try:
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

    # 2. Check for Excel files
    excel_files = list(excel_dir.glob("*.xlsx")) + list(excel_dir.glob("*.xls"))
    if not excel_files:
        print(f"Error: No Excel files (.xlsx, .xls) found in '{excel_dir}'.")
        sys.exit(1)

    # 3. Check for valid image files
    photo_extensions = {".jpg", ".jpeg"}
    photos = [p for p in photo_dir.rglob("*") if p.is_file() and p.suffix.lower() in photo_extensions]
    if not photos:
        print(f"Error: No valid image files (.jpg, .jpeg) found in '{photo_dir}'.")
        sys.exit(1)

    # 4. Prompt if output_dir exists and is non-empty
    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        response = input(f"Warning: Output directory '{output_dir}' already exists and is non-empty.\nDo you want to overwrite/append? [y/N]: ")
        if response.lower() not in ['y', 'yes']:
            print("Operation aborted by user.")
            sys.exit(0)

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

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        unmatched_dir.mkdir(parents=True, exist_ok=True)
        no_gps_dir.mkdir(parents=True, exist_ok=True)

    gcp_df, pre_dedup_count, post_dedup_count = process_excel_files(excel_files)
    dedup_removed = pre_dedup_count - post_dedup_count

    total_photos = len(photos)
    photos_matched_count = 0
    unmatched_photos_count = 0
    matched_dict = {row['ID']: [] for _, row in gcp_df.iterrows()}

    # TQDM Bar 2: EXIF extraction and distance calculation
    # We will also queue up copy operations for Bar 3
    copy_queue = [] # list of tuples: (source_path, dest_path, is_unmatched, gcp_id)

    for photo_path in tqdm(photos, desc="Scanning EXIF & Calculating Distances"):
        lat, lon = get_gps_from_exif(photo_path)

        if lat is None or lon is None:
            # No GPS
            copy_queue.append((photo_path, no_gps_dir / photo_path.name, True, None))
            unmatched_photos_count += 1
            continue

        matched_any = False

        # Check against all GCPs
        for idx, row in gcp_df.iterrows():
            gcp_lat = row['latitude']
            gcp_lon = row['longitude']

            if pd.isna(gcp_lat) or pd.isna(gcp_lon):
                continue

            try:
                gcp_lat = float(gcp_lat)
                gcp_lon = float(gcp_lon)
            except ValueError:
                continue

            dist = geodesic((lat, lon), (gcp_lat, gcp_lon)).meters

            if dist <= args.buffer_distance:
                matched_any = True
                gcp_id = row['ID']
                gcp_name = row['point_name']

                # Queue matched copy
                gcp_folder = output_dir / f"GCP_{gcp_id}_{gcp_name}"
                dest_name = f"GCP_{gcp_id}_{photo_path.name}"
                copy_queue.append((photo_path, gcp_folder / dest_name, False, gcp_id))

        if matched_any:
            photos_matched_count += 1
        else:
            # Unmatched
            copy_queue.append((photo_path, unmatched_dir / photo_path.name, True, None))
            unmatched_photos_count += 1

    # TQDM Bar 3: Copying/Moving files
    generated_copies_count = 0
    moved_sources = set()

    if not args.dry_run:
        for src, dest, is_unmatched, gcp_id in tqdm(copy_queue, desc="Copying/Moving Photos"):
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Always copy to ensure we don't break if a photo matches multiple GCPs
            shutil.copy2(src, dest)
            if args.copy_mode == 'move':
                moved_sources.add(src)

            if not is_unmatched and gcp_id is not None:
                matched_dict[gcp_id].append(src.name)
                generated_copies_count += 1

        # Clean up source files if in move mode
        if args.copy_mode == 'move':
            for src in moved_sources:
                if src.exists():
                    src.unlink()
    else:
        # Just populate matched_dict based on queue for dry-run report
        for src, dest, is_unmatched, gcp_id in copy_queue:
            if not is_unmatched and gcp_id is not None:
                matched_dict[gcp_id].append(src.name)
                generated_copies_count += 1

    # Update DataFrame with results
    matched_gcps_count = 0
    for idx, row in gcp_df.iterrows():
        gcp_id = row['ID']
        matched_photos = matched_dict[gcp_id]
        if matched_photos:
            gcp_df.at[idx, 'PhotoCheck_Or_Not'] = 'Yes'
            gcp_df.at[idx, 'Matched_Photos'] = ', '.join(matched_photos)
            matched_gcps_count += 1

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
    print(f"Points with Matching Photos     : {matched_gcps_count}")
    print(f"Points with ZERO Photos         : {points_no_photos}")
    print("-" * 60)
    print(f"Matched Photos Count (Unique)   : {photos_matched_count}")
    print(f"Matched Photos (Total Copies)   : {generated_copies_count}")
    print(f"Unmatched Photos Count          : {unmatched_photos_count}")
    print("="*60)
    if args.dry_run:
        print("Dry run enabled. No report exported.")
    else:
        print(f"Report exported to:\n  {report_path.resolve()}")
    print("="*60)

if __name__ == "__main__":
    main()
