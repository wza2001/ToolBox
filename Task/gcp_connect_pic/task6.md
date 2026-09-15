### Task 6: Directory Scaffolding, File Distribution & Report Generation

Hello Jules, let's complete the script with the directory scaffolding, physical file distribution, and Excel report export:

1. **Strict Folder Scaffolding**:
   - Pre-create dedicated folders for **every** GCP point immediately after deduplication using numeric IDs: `output_dir / GCP_{ID}` (even if a point matches 0 photos).
   - Create the tracking folders:
     - `output_dir / Manual_Calibration` (for conflict/ambiguous photos)
     - `output_dir / Inconnect_photo / No_GPS`
     - `output_dir / Inconnect_photo / Out_of_Range`
     - `output_dir / Inconnect_photo / Time_Mismatch`

2. **File Distribution (`shutil.copy2` / move)**:
   - Uniquely matched photos: copy/move to `GCP_{ID} / {photo_name}`.
   - Conflicting photos: copy/move to `Manual_Calibration / {photo_name}`.
   - Unmatched photos: route to their corresponding `Inconnect_photo` subfolder.

3. **Summary Excel Report (`RawGCP_YYYYMMDD.xlsx`)**:
   - Retain core columns: `ID`, `point_name`, `latitude`, `longitude`, `altitude`, `north`, `east`, `Recorded at`.
   - Add updated tracking columns:
     - `PhotoCheck_Or_Not`: `'Yes'`, `'Conflict'`, or `'No'`.
     - `Matched_Count`: Integer count of uniquely matched photos.
     - `Matched_Photos`: Comma-separated list of filenames.
     - `Conflict_Photos`: Comma-separated list of conflict filenames routed to `Manual_Calibration`.

Please assemble and provide the final, complete `gcp_processor.py` script.