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
    parser = argparse.ArgumentParser(description="Process GCPs and categorize photos based on distance.")
    parser.add_argument("--excel_dir", type=str, required=True, help="Directory containing Excel files.")
    parser.add_argument("--photo_dir", type=str, required=True, help="Directory containing photos.")
    parser.add_argument("--output_dir", type=str, required=True, help="Output directory for categorized outputs.")
    parser.add_argument("--buffer_distance", type=float, default=50.0, help="Buffer threshold in meters (default: 50.0).")
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

def process_excel_files(excel_dir):
    excel_dir_path = Path(excel_dir)
    all_files = list(excel_dir_path.glob("*.xlsx")) + list(excel_dir_path.glob("*.xls"))

    if not all_files:
        raise ValueError(f"No Excel files found in {excel_dir}")

    df_list = []
    for f in all_files:
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
    merged_df = merged_df.drop_duplicates(subset=['point_name', 'latitude', 'longitude'])

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

    return merged_df

def main():
    args = parse_args()

    excel_dir = Path(args.excel_dir)
    photo_dir = Path(args.photo_dir)
    output_dir = Path(args.output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    unmatched_dir = output_dir / "Inconnect_photo"
    no_gps_dir = unmatched_dir / "No_GPS"

    unmatched_dir.mkdir(exist_ok=True)
    no_gps_dir.mkdir(exist_ok=True)

    print("Processing Excel files...")
    gcp_df = process_excel_files(excel_dir)

    # List all photos
    photo_extensions = {".jpg", ".jpeg"}
    photos = [p for p in photo_dir.rglob("*") if p.is_file() and p.suffix.lower() in photo_extensions]

    total_photos = len(photos)
    photos_matched_count = 0
    unmatched_photos_count = 0

    matched_dict = {row['ID']: [] for _, row in gcp_df.iterrows()}

    print(f"Found {total_photos} photos. Processing...")

    for photo_path in tqdm(photos, desc="Processing Photos"):
        lat, lon = get_gps_from_exif(photo_path)

        if lat is None or lon is None:
            # No GPS
            shutil.copy2(photo_path, no_gps_dir / photo_path.name)
            unmatched_photos_count += 1
            continue

        matched_any = False

        # Check against all GCPs
        for idx, row in gcp_df.iterrows():
            gcp_lat = row['latitude']
            gcp_lon = row['longitude']

            # Skip if invalid GCP coordinates
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

                # Copy to matched folder
                gcp_folder = output_dir / f"GCP_{gcp_id}_{gcp_name}"
                gcp_folder.mkdir(exist_ok=True)

                dest_name = f"GCP_{gcp_id}_{photo_path.name}"
                shutil.copy2(photo_path, gcp_folder / dest_name)

                matched_dict[gcp_id].append(photo_path.name)

        if matched_any:
            photos_matched_count += 1
        else:
            # Unmatched
            shutil.copy2(photo_path, unmatched_dir / photo_path.name)
            unmatched_photos_count += 1

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
    gcp_df.to_excel(report_path, index=False)

    # Print summary
    print("\n" + "="*40)
    print(" SUMMARY")
    print("="*40)
    print(f"Total GCPs processed        : {len(gcp_df)}")
    print(f"GCPs with matched photos    : {matched_gcps_count}")
    print(f"Total photos processed      : {total_photos}")
    print(f"Photos matched to GCPs      : {photos_matched_count}")
    print(f"Unmatched photos            : {unmatched_photos_count}")
    print("="*40)
    print(f"Report exported to: {report_path}")

if __name__ == "__main__":
    main()
