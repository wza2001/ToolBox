### Task 4: Data Ingestion & Robust Datetime Parsing Helpers

Hello Jules, let's start the refactoring by upgrading the data ingestion and datetime extraction modules in `gcp_processor.py`:

1. **Robust Excel & CSV Ingestion**:
   - In `check_preflight()` and `process_excel_files()`, scan for `.xlsx`, `.xls`, and `.csv` files (exclude temporary files prefixed with `~$`).
   - Handle CSV encoding failures by trying `utf-8-sig`, then falling back to `gbk` or `latin1`.
   - Parse the `Recorded at` column into standard Python `datetime` (naive). Handle `pd.Timestamp`, ISO strings, and slashes (`/` or `-`).

2. **EXIF Datetime Parsing Helper (`get_photo_datetime(image_path)`)**:
   - Implement a helper to extract shooting time from EXIF tags `DateTimeOriginal` (Tag 36867), falling back to `DateTime` (Tag 306).
   - Convert the standard EXIF datetime format (`"YYYY:MM:DD HH:MM:SS"`) into a naive `datetime` object.
   - Ensure all comparisons are timezone-naive to avoid `offset-naive vs offset-aware` runtime exceptions.

Please provide only the updated helper functions and file reading routines for this stage.