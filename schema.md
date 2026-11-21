# Photo record (shared contract with the rest of the team)

```json
{
  "id": "a1b2c3d4",
  "file": "uploads/a1b2c3d4.jpg",
  "original_name": "IMG_0412.jpg",
  "category": "Nachtrag evidence",
  "category_source": "model | user",
  "confidence": 0.82,
  "detections": [{"class": "rock", "confidence": 0.82, "x": 320, "y": 210, "width": 140, "height": 90}],
  "lat": 48.15, "lon": 11.58,
  "location_source": "exif | site_default | user",
  "taken_at": "2026-11-21T09:14:00",
  "note": ""
}
```
Categories: progress, delivery, defect, Nachtrag evidence, obstruction, safety, uncategorized.
Detections are suggestions. The site manager confirms or reassigns (category_source flips to "user", then AI never overwrites it).
