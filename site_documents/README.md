# site_documents – test data for site layout generation (fictitious)

Fictitious bridge site "BW 27 über den Erlbach". Everything is invented. The files exist to test
the AI manager ("Generate the site layout"), `POST /api/inbox/import` (chat attachments), `POST /api/site/sources` and `POST /api/site/layout/suggest`, which build a draft `site_layout.json` from
coordinates found in site documents and the EXIF GPS of uploaded photos.

**Anchor:** 48.2935 N / 11.8890 E. This is deliberately not the anchor of `backend/data` (48.3069 / 11.9081), so a test can
tell which data a layout came from. The plan points north. The bridge runs west → east: W1 · A1 · (Erlbach) · A2 · W2, with
the site facilities (BE) to the south-west.

Regenerate everything with `python site_documents/generate.py`. The ground truth is defined once there, in plan metres.

- **`upload/`**: attach these in the AI manager chat (documents + photos in one message), or in 3D twin → Layout → "Add site documents…". Then ask "Generate the site layout" or press the button in the reply.
- **`ground_truth/`**: used by the tests only. Don't upload these; `photo_positions.csv` would add unnamed points.

| File | What it contains | What it tests |
|---|---|---|
| `upload/project_reference.json` | Anchor point, CRS, `rotation_deg`, project name | Origin taken from an explicit anchor |
| `upload/vermessung_punkte.csv` | Survey point list `id;bezeichnung;typ;breite;laenge` (WGS84, decimal commas): anchor BP0, boundary B1–B5, 4 corners each for W1/A1/A2/W2/BE | CSV header detection, corner grouping `W1-1…W1-4` → zone `w1`, boundary |
| `upload/bauzeitenplan.xlsx` | Schedule `W1_BP … W2_BET` + `UB1_MONT` (no position), centre of each structure in UTM 32N with the zone prefix (`32 714 …`) | XLSX, UTM → WGS84, linking activities to zones, unmatched id reported |
| `upload/baugrundgutachten.pdf` | Geotechnical report (text layer): boreholes BK1–BK2 in UTM + WGS84, BK3–BK4 in UTM only | Coordinates in PDF text, label detection |
| `upload/baugrundgutachten.docx` | Same boreholes as a Word table (Rechtswert/Hochwert + Breite/Länge) | DOCX table, de-duplication with the PDF |
| `upload/lageplan.geojson` | Zone polygons (lon, lat order) + crane KR-01 as a point | GeoJSON polygons / points |
| `upload/photos/site_*.jpg` | Copies of the 7 originals in `backend/data/seed/uploads/` with GPS, direction, accuracy and time written to EXIF | Photo placement by GPS |
| `ground_truth/photo_positions.csv` | What was written into each photo and the expected zone / plan position | Photo ground truth |
| `ground_truth/expected_layout.json` | Ground truth in metres (zones, centroids, markers, photo zones, distances, unmatched activities) | Assertions in `backend/tests/test_layout_suggest.py` |
| `ground_truth/example_site_layout.json` | The layout the API produced from all of the above (end-to-end run) | Reference output |

## Deliberate cases in the photos
- `07179547` ↔ `a7b1a4f1`: exactly **25.0 m** apart (A1 ↔ A2).
- `ecae8902` ↔ `8d694186`: **2.0 m** apart at ±4 / ±5 m GPS accuracy, so they count as the same spot.
- `1c92357b`: direction 270° with **magnetic** reference (`M`). Stored as 273.5° true north (declination 3.5°, `MAGNETIC_DECLINATION_DEG`).
- `6342cd1c`: excavator inside the site facilities (BE). The `machine_in_restricted_zone` rule should fire.
- `4d007fe8`: GPS in Tokyo. Must be reported as an outlier and never drawn.

## Not covered (by design)
- Reading shapes from a drawn plan (Grundriss) or a scan: only coordinates written as text or in tables are used.
- Gauß-Krüger / DHDN coordinates: these need a datum shift and are rejected rather than guessed.
- Uploading the schedule as a site document only links its ids to zones. It does not load the schedule into the planner (`/api/demo/load` or the schedule import does that).
