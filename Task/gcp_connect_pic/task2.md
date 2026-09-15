Great! Now please write a companion Python test script `create_mock_dataset.py` to verify the functionality of the tool:

1. **Mock Excel Files**:
   - Create 2 distinct Excel files (`points_part1.xlsx`, `points_part2.xlsx`) in a test folder.
   - Fill them with sample data matching the columns (`point_name`, `latitude`, `longitude`, `altitude`, `north`, `east`, `Recorded at`, etc.).
   - Include 4 sample points:
     - Point 1: `(24.498533, 54.375940)`
     - Point 2: Close to Point 1 (around 60 meters away, so buffer zones overlap)
     - Point 3: Independent point far away
     - Point 4: Duplicate of Point 1 (to test deduplication logic).

2. **Mock Images with EXIF GPS**:
   - Generate 5 minimal blank JPEG files using `Pillow` and inject valid GPS EXIF tags using `piexif`:
     - Image A: 10m from Point 1 (should match Point 1 only).
     - Image B: Exactly in the overlapping 50m zone of both Point 1 and Point 2 (should trigger the multi-copy duplicate rule).
     - Image C: 500m away from all points (should land in `Inconnect_photo`).
     - Image D: No GPS tags injected (should land in `Inconnect_photo/No_GPS` or `Inconnect_photo`).
     - Image E: 15m from Point 3 (should match Point 3).

3. Provide a one-line command showing how to run the main tool against this generated mock dataset.