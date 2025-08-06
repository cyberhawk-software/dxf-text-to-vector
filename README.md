# DXF Text to GeoJSON Vector Converter

This Python script extracts TEXT and MTEXT entities from a DXF file, including those nested within INSERT (block) entities. It converts each character into a vector polygon outline, centers the text strings on their insertion points, transforms the coordinates to a standard geospatial projection (WGS84), and saves the result as a GeoJSON file.

This tool is ideal for preparing CAD text data for use in GIS applications like QGIS, ArcGIS, or web mapping platforms like Mapbox, where text needs to be represented as true geometry rather than just labels.

## Features

✅ Character-level Vectorization: Converts each character into a filled polygon, not just a point.

✅ Block Support: Automatically "explodes" INSERT entities to find and process text within block definitions.

✅ Text Centering: Accurately centers both single-line (TEXT) and multi-line (MTEXT) entities on their DXF insertion points.

✅ CRS Transformation: Uses pyproj to transform coordinates from any specified source CRS to WGS84 (EPSG:4326).

✅ Flexible Font Handling: Allows you to specify a .ttf font file for rendering. If the font is not found, it gracefully falls back to a system default.

✅ String Exclusion: Provides an option to exclude specific strings (e.g., "0", "0.0") from the output.

✅ Optimized: Caches character glyphs to significantly speed up processing on files with repetitive text.


<img width="400" height="350" alt="Screenshot From 2025-08-05 08-44-27" src="https://github.com/user-attachments/assets/3f5acd87-8277-4824-b69b-0570a5ffd791" />

## Requirements
- Python 3.7+
-- ezdxf
-- numpy
-- pyproj
-- shapely
-- geojson
-- matplotlib

## Installation 

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage 

The script is run from the command line and accepts several arguments to control its behavior.

### Command 
```bash
python dxfTextToVector.py --input <path_to_dxf> --output <path_to_geojson> --font <path_to_ttf> [options]
```

### Arguments
**--input** *(Required)*: Path to the input DXF file.

**--output** *(Required)*: Path for the generated output GeoJSON file.

**--font** *(Required)*: Path to the .ttf font file to use for rendering all text (e.g., 'C:/Windows/Fonts/arial.ttf').

**--source_crs** *(Optional)*: The source Coordinate Reference System of the DXF file (e.g., 'EPSG:27700'). Defaults to 'EPSG:4326'.

**--exclude_strings** *(Optional)*: A space-separated list of strings to exclude from processing. Defaults to ['0', '0.0'].

### Examples

**Basic Usage (using British National Grid as source CRS)**:

```bash
python dxfTextToVector.py \
    --input "my_cad_file.dxf" \
    --output "output_vectors.geojson" \
    --font "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf" \
    --source_crs "EPSG:27700"
```

**Excluding Additional Strings:**

This command will skip any text entities that are exactly "N/A" or "TEMP", in addition to the defaults.

```bash
python dxf_condxfTextToVectorverter.py \
    --input "plans.dxf" \
    --output "output_vectors.geojson" \
    --font "C:/Windows/Fonts/verdana.ttf" \
    --source_crs "EPSG:32610" \
    --exclude_strings "N/A" "TEMP"
```

**Generate vector tiles:**

To generate an MBTiles file combining both geometry and label layers, use Tippecanoe. This example demonstrates how to include:

- **Geometry layer** (e.g., generated with ogr2ogr)
- **Label layer** from output_vectors.geojson


```bash
tippecanoe \
  -o <path_to_output_mbtiles> \
  -L geometry:"<path_to__geometry_geojson>" \
  -L labels:"<path_to_labels_geojson>" \  
  --force \
  --drop-densest-as-needed \
  --minimum-zoom=8 \
  --maximum-zoom=16
```

## License

This project is licensed under the MIT License.