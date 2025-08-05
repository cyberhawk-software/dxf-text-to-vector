# DXF text to vector 

`dxfTextToVector.py` - this script extracts all TEXT and MTEXT from a DXF file and stores them in a GeoJSON file. Each letter as outline vector value.

✅ Reads a DXF file 

✅ Extracts all TEXT/MTEXT entities

✅ Converts them to vector polygon outlines (font-based). Produces real vector outlines, not just text attributes.

✅ Saves them as a GeoJSON file

<img width="835" height="774" alt="Screenshot From 2025-08-05 08-44-27" src="https://github.com/user-attachments/assets/3f5acd87-8277-4824-b69b-0570a5ffd791" />


## Usage example

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the script:

```bash
python dxfTextToVector.py \
  --input '/path/to/your_file.dxf' \
  --output '/output/text_outlines.geojson' \
  --source_crs "EPSG:4326" \
  --font "/usr/share/fonts/truetype/freefont/FreeMono.ttf" \
  --exclude_strings "0" "0.0"
```

Use `output/text_outlines.geojson` as a source in Mapbox or in `typecannoe` combining with ogr2ogr script geoJson results.



```bash
# Convert the geometry and labels to MBTiles format using Tippecanoe
tippecanoe \
  -o "$OUTPUT_MBtiles" \
  -L geometry:"$GEOM_GEOJSON" \
  -L labels:"$LABELS_GEOJSON" \  
  --force \
  --drop-densest-as-needed \
  --minimum-zoom=8 \
  --maximum-zoom=16
```
