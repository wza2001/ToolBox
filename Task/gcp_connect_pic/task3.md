Hello Jules, let's specify a dedicated Task for building a robust and user-friendly CLI (Command Line Interface) for the GCP-Photo Matching Tool. 

Please structure the CLI implementation according to the following specifications:

### 1. Argument Parsing Specifications (`argparse`)
Implement a dedicated `parse_args()` function with clean help messages and validation:
- `-e, --excel-dir` (Required): Path to the folder containing GCP Excel files (`.xlsx`, `.xls`).
- `-p, --photo-dir` (Required): Path to the folder containing aerial/ground photos.
- `-o, --output-dir` (Optional, default: `./GCP_Photo_Output`): Path where organized folders and reports will be saved.
- `-b, --buffer` (Optional, type=float, default=50.0): Buffer radius in meters for spatial matching.
- `--dry-run` (Optional, flag / store_true): Run the spatial analysis and print the match results/table WITHOUT copying or modifying any actual photo files.
- `--copy-mode` (Optional, choices=['copy', 'move'], default='copy'): Choose whether to duplicate photos into GCP folders or move them.

### 2. Path Validation & Pre-flight Checks
Before executing the heavy operations, the CLI must:
1. Verify that `excel_dir` and `photo_dir` exist and are accessible directories.
2. Check if there is at least one `.xlsx` or `.xls` file in `excel_dir`.
3. Check if there are valid image files (`.jpg`, `.jpeg`) in `photo_dir`.
4. Prompt an interactive warning if `output_dir` already exists and is non-empty, asking whether to overwrite or append (suppressed if a `--force` flag is provided).

### 3. Visual Feedback & CLI Output UX
- **Banner**: Print an ASCII or clean text banner when starting (showing tool name and configured parameters).
- **Progress Bars (`tqdm`)**:
  - Bar 1: Reading and deduplicating Excel GCP points.
  - Bar 2: Extracting EXIF and calculating spatial distances for photos.
  - Bar 3: Copying/moving matched photos to output directories.
- **Summary Report**: Render a neat terminal summary table using standard formatting or `rich`/`tabulate` (with fallback to ASCII table), summarizing:
  - Total GCP points loaded (and duplicate count removed)
  - Total photos scanned
  - Points with matching photos vs. Points with zero photos
  - Matched photos count (including duplicate copies generated)
  - Unmatched photos count (routed to `Inconnect_photo`)
  - Full path of the generated `RawGCP_YYYYMMDD.xlsx` report.

Please provide the modular code for this CLI layer and show how it seamlessly connects to the core processing engine.