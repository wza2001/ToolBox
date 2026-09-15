Hello Jules, I need you to write a production-grade, highly robust Python tool for processing aerial survey ground control points (GCP) and categorizing georeferenced photos.

### 1. Requirements & Workflow
1. **Input**:
   - `excel_dir`: Directory containing one or more Excel files (`.xlsx`, `.xls`).
   - `photo_dir`: Directory containing drone/ground photos (`.jpg`, `.jpeg`).
   - `output_dir`: Target directory for categorized outputs.
   - `buffer_distance`: Buffer threshold in meters (default: `50.0`).

2. **Excel Processing**:
   - Merge all Excel files inside `excel_dir`.
   - The files contain columns such as: `point_name`, `说明`, `latitude`, `longitude`, `altitude`, `north`, `east`, `elevation`, `point_type`, `Recorded at`, etc.
   - Deduplicate rows based on `point_name` and coordinates.
   - Assign a new incremental integer `ID` starting from `1` for each unique point.
   - Filter and retain core attributes: `ID`, `point_name`, `latitude`, `longitude`, `altitude`, `north`, `east`, `Recorded at`.
   - Add two new tracking columns:
     - `PhotoCheck_Or_Not`: Boolean / string flag (`Yes` or `No`) indicating whether any photo matched this point.
     - `Matched_Photos`: Comma-separated list of filenames matched within the buffer.

3. **Spatial Matching & File Operations**:
   - Read GPS coordinates (Latitude, Longitude) directly from each image's EXIF metadata. Safely convert DMS rational values to decimal degrees (WGS84).
   - Compute the great-circle / geodesic horizontal distance between each image and each GCP (e.g., using `geopy.distance.geodesic` or Haversine formula).
   - **Matching Condition**: If distance $\le buffer\_distance$ (50m):
     - Associate the photo with the GCP's new ID.
     - Copy the photo (`shutil.copy2`) into an output folder named `GCP_{ID}_{point_name}/`.
   - **Multi-point Overlap**: If a single photo falls within the 50m radius of multiple GCPs, generate a physical copy in each matched GCP folder. Prefix or tag the filename (e.g., `GCP_{ID}_{filename}`) to avoid collision while maintaining lineage.
   - **Unmatched Photos**: Any photo with distance > 50m from all points, or photos lacking valid GPS EXIF data, must be copied into an `Inconnect_photo/` directory.

4. **Export Report**:
   - Export the consolidated point table to an Excel file named `RawGCP_YYYYMMDD.xlsx` (dynamically formatted using the current system execution date) inside `output_dir`.

### 2. Engineering & Code Standards
- Use `argparse` for flexible CLI execution:
  - `--excel_dir`, `--photo_dir`, `--output_dir`, `--buffer_distance` (default: 50.0).
- Libraries: `pandas`, `openpyxl`, `piexif` or `exifread`, `geopy` (or vectorized Haversine calculation), `tqdm`, `pathlib`.
- Handle edge cases gracefully:
  - Non-numeric or missing GPS data in EXIF must not crash the script (route to `Inconnect_photo/No_GPS`).
  - Windows vs. Linux path separators must be handled transparently using `pathlib.Path`.
- Display a progress bar with `tqdm` during photo processing, and print a summary table at the end showing: total GCPs, GCPs with matched photos, total photos processed, photos matched, and unmatched photos.

Please provide clean, well-commented, production-ready Python code.