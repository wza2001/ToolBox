Hello Jules, we need to update the matching logic in `gcp_processor.py` from an **AND** condition to an **OR (Relaxed Recall)** condition, while implementing priority arbitration and timezone alignment.

Please refactor the matching and classification logic according to the following specifications:

---

### 1. Robust Timezone Alignment (`parse_datetime` & `get_photo_datetime`)
- **GCP Recorded Time**: RTK timestamps in the `Recorded at` column often use ISO 8601 UTC strings ending with `'Z'` (e.g., `2026-09-14T13:07:39.154Z`)[cite: 2].
  - Use `pd.to_datetime` to parse the string[cite: 2].
  - If timezone-aware, convert to Abu Dhabi local time (`Asia/Dubai`, UTC+4) and strip `tzinfo` to make it naive datetime[cite: 2].
- **Photo EXIF Time**: Read `DateTimeOriginal` (tag 36867) from the Exif SubIFD (`exif.get_ifd(0x8769)`), falling back to root tags `36867` or `306`[cite: 2]. Convert to naive datetime[cite: 2].

---

### 2. OR-Based Candidate Matching & Confidence Scoring
For each photo, test it against all candidate GCPs. A photo qualifies as a candidate for a GCP if it satisfies **EITHER** or **BOTH** criteria:
1. **Spatial Match**: Geodesic distance $\le \text{buffer\_distance}$ (default: `50.0` m)[cite: 2].
2. **Temporal Match**: $|\text{Time}_{\text{photo}} - \text{Time}_{\text{GCP}}| \le \text{time\_window}$ (default: `300` seconds)[cite: 2].

Assign a confidence tier to each qualifying candidate pair:
- **Tier 1 (`HIGH`)**: Both Spatial AND Temporal criteria match.
- **Tier 2 (`SPATIAL_ONLY`)**: Spatial matches, but Temporal fails or is unavailable.
- **Tier 3 (`TEMPORAL_ONLY`)**: Temporal matches, but Spatial fails or photo has no GPS.

---

### 3. Priority Arbitration & Conflict Routing
Evaluate the qualifying candidate GCPs for each photo:

- **Single Candidate**:
  - Assign photo directly to that GCP's folder: `output_dir / GCP_{ID} / {photo_name}`[cite: 2].
  - Track the match basis (`Both`, `Spatial_Only`, or `Temporal_Only`).
- **Multiple Candidates (Conflict Resolution)**:
  - Find the highest confidence tier among the matched candidates.
  - If exactly **one** candidate holds the highest tier (e.g., one GCP is `HIGH` while others are `TEMPORAL_ONLY`), award the match to that single winner.
  - If **two or more** candidates tie for the highest tier (e.g., two points both match at `HIGH` or both at `SPATIAL_ONLY`), flag the photo as `CONFLICT`. Route it exclusively to `output_dir / Manual_Calibration / {photo_name}`[cite: 2] and record all tied GCP IDs.
- **Zero Candidates (Unmatched)**:
  - Route to `output_dir / Inconnect_photo / {photo_name}`[cite: 2] (or `No_GPS` if GPS tags are completely absent)[cite: 2].

---

### 4. Output Reporting & Folder Management
- Ensure pre-creation of all `GCP_{ID}` folders (even if 0 photos matched)[cite: 2].
- In the summary Excel report (`RawGCP_YYYYMMDD.xlsx`), ensure the following columns exist[cite: 2]:
  - `ID`, `point_name`, `latitude`, `longitude`, `altitude`, `north`, `east`, `Recorded at`[cite: 2].
  - `PhotoCheck_Or_Not`: `'Yes'`, `'Conflict'`, or `'No'`[cite: 2].
  - `Matched_Count`: Count of uniquely assigned photos[cite: 2].
  - `Matched_Photos`: Comma-separated list of filenames[cite: 2].
  - `Conflict_Photos`: Comma-separated list of conflicting filenames routed to manual calibration[cite: 2].
  - `Match_Basis`: Comma-separated breakdown of matched criteria (e.g., `IMG_2550.JPG (Both)`).

Please update `gcp_processor.py` with these rules and print an updated terminal summary showing counts for `HIGH`, `SPATIAL_ONLY`, `TEMPORAL_ONLY`, `CONFLICT`, and `UNMATCHED`.