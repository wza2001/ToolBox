### Task 5: Dual-Verification & Conflict Arbitration Engine

Hello Jules, now let's implement the core spatial-temporal matching and conflict arbitration logic in `gcp_processor.py`:

1. **CLI Argument**:
   - Add `-t, --time-window` (type=int, default=300, help="Maximum allowed time difference in seconds between photo and GCP timestamp").

2. **Two-Stage Cascaded Evaluation**:
   For each photo:
   - If EXIF GPS is missing, classify as `NO_GPS`.
   - Find all candidate GCPs where geodesic distance $\le \text{buffer\_distance}$. If none, classify as `OUT_OF_RANGE`.
   - Among spatial candidates, calculate $|\Delta t| = |\text{Time}_{\text{photo}} - \text{Time}_{\text{GCP}}|$. Keep only candidates where $|\Delta t| \le \text{time\_window}$.
   - If candidates exist spatially but none satisfy the time window, classify as `TIME_MISMATCH`.

3. **Conflict Arbitration**:
   - **Unique Match (Exactly 1 valid GCP candidate)**: Assign photo to that GCP's match collection.
   - **Ambiguous Conflict ($\ge 2$ valid GCP candidates)**: Mark photo as `CONFLICT` and track all associated candidate GCP IDs for reporting.

Do not write the file movement/copying logic yet—focus on returning clean structured match dictionaries and status classifications.