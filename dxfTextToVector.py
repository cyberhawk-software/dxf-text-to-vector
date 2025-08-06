# -*- coding: utf-8 -*-
#
# Author: Vitalij L. 
# License: MIT
#
# Purpose: Extract TEXT and MTEXT entities from a DXF file, including those
# within block references (INSERTs). Converts each character to a vector
# polygon outline using a specified font, transforms coordinates, and saves
# as a GeoJSON file.
#
import os
import argparse
import ezdxf
import numpy as np
import pyproj
from ezdxf.entities import Text, MText
from ezdxf.math import OCS, BoundingBox
from shapely.geometry import Polygon, mapping
from geojson import Feature, FeatureCollection, dump
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties, findfont

# --- Global Cache ---
# Cache TextPath objects to avoid regenerating them for the same character.
# This significantly improves performance on files with lots of text.
TEXT_PATH_CACHE = {}

# --- Configuration ---
# The target CRS is fixed to WGS84, the standard for GeoJSON.
TARGET_CRS = "EPSG:4326"

# --- Helper Functions ---

def get_font_properties(font_path: str) -> FontProperties:
    """
    Checks if a font path is valid and returns FontProperties.
    Falls back to a system default sans-serif font if the path is invalid.
    """
    if font_path and os.path.exists(font_path):
        # If the path is valid, use it directly.
        return FontProperties(fname=font_path)
    else:
        # If the path is invalid or not provided, issue a warning and find a default.
        print(f"Warning: Font not found at '{font_path}'. Falling back to system default sans-serif font.")
        default_font_path = findfont(FontProperties(family="sans-serif"))
        return FontProperties(fname=default_font_path)


def get_char_path(char: str, font_prop: FontProperties, size: float) -> TextPath:
    """
    Creates a matplotlib TextPath for a single character, using a cache to avoid
    redundant work.
    """
    # Generate a unique key for the cache
    cache_key = (char, font_prop.get_name(), size)
    if cache_key in TEXT_PATH_CACHE:
        return TEXT_PATH_CACHE[cache_key]

    try:
        # Create the path and store it in the cache
        path = TextPath((0, 0), char, size=size, prop=font_prop)
        TEXT_PATH_CACHE[cache_key] = path
        return path
    except Exception as e:
        print(f"Warning: Could not create text path for character '{char}'. Error: {e}")
        return None


def transform_text_entity(entity: Text, transformer: pyproj.Transformer, font_prop: FontProperties, exclude_strings: list) -> list[Feature]:
    """
    Processes a single TEXT entity, centering it on its insertion point.
    """
    text_string = entity.dxf.text
    # Skip this entity if its text is in the exclusion list
    if text_string in exclude_strings:
        print(f"  Skipping excluded string: '{text_string}'")
        return []

    features = []
    doc = entity.doc
    if not doc:
        return []

    # Get text properties
    insert_point = np.array(entity.dxf.insert)
    height = entity.dxf.height
    rotation = entity.dxf.rotation
    layer = entity.dxf.layer
    font_name = font_prop.get_name()
    ocs = entity.ocs()

    # --- Centering Logic ---
    # 1. Calculate the total width of the string to determine the offset.
    total_width = 0.0
    for char in text_string:
        if char.isspace():
            total_width += height * 0.5  # Approximation for space width
            continue
        
        char_path = get_char_path(char, font_prop, size=height)
        if char_path:
            try:
                total_width += char_path.get_extents().width
            except Exception:
                total_width += height * 0.5 # Fallback

    # 2. Define the rotation matrix for the text entity
    rad = np.deg2rad(rotation)
    rot_matrix = np.array([[np.cos(rad), -np.sin(rad), 0], [np.sin(rad), np.cos(rad), 0], [0, 0, 1]])

    # 3. Calculate the offset vector to shift the start position
    offset_vector = np.array([-total_width / 2.0, 0, 0])
    rotated_offset = offset_vector @ rot_matrix.T[:3,:3]

    # 4. Set the starting position by applying the offset to the original insertion point.
    current_pos = insert_point + rotated_offset
    
    # --- Character Processing ---
    for char in text_string:
        char_path = get_char_path(char, font_prop, size=height)
        if char_path is None:
            continue
        
        try:
            char_width = char_path.get_extents().width
        except Exception:
            char_width = height * 0.5

        if not char.isspace():
            transformed_verts = []
            for point in char_path.vertices:
                vec = np.array([point[0], point[1], 0])
                rotated_vec = vec @ rot_matrix.T[:3, :3]
                final_vec_ocs = current_pos + rotated_vec
                final_vec_wcs = ocs.to_wcs(final_vec_ocs)
                lon, lat = transformer.transform(final_vec_wcs[0], final_vec_wcs[1])
                transformed_verts.append((lon, lat))

            if len(transformed_verts) >= 3:
                polygon = Polygon(transformed_verts)
                feature = Feature(
                    geometry=mapping(polygon),
                    properties={
                        "text": text_string, "char": char, "layer": layer, "font": font_name,
                        "insert_x_wcs": float(insert_point[0]), "insert_y_wcs": float(insert_point[1]),
                    }
                )
                features.append(feature)
        
        # Advance position for the next character
        advance = np.array([char_width, 0, 0])
        current_pos += advance @ rot_matrix.T[:3,:3]
        
    return features


def transform_mtext_entity(entity: MText, transformer: pyproj.Transformer, font_prop: FontProperties, exclude_strings: list) -> list[Feature]:
    """
    Processes a single MTEXT entity, handling multi-line content and centering the entire block.
    """
    # MTEXT content can have complex formatting; `plain_text()` provides a clean version.
    text_content = entity.plain_text()
    if text_content in exclude_strings:
        print(f"  Skipping excluded string: '{text_content}'")
        return []

    all_features = []
    # Use the `virtual_entities()` method to get text fragments with transformations applied.
    # This is more robust than `fragments()` for handling complex MTEXT.
    for line in entity.virtual_entities():
        # Each line is essentially a TEXT entity, so we can reuse the same logic.
        all_features.extend(transform_text_entity(line, transformer, font_prop, exclude_strings))
        
    return all_features


def dxf_to_geojson(dxf_path: str, geojson_path: str, font_path: str, source_crs: str, exclude_strings: list):
    """
    Main function to drive the DXF to GeoJSON conversion process.
    """
    print(f"Loading DXF file: {dxf_path}")
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except (IOError, ezdxf.DXFStructureError) as e:
        print(f"Error reading DXF file: {e}")
        return

    # Get font properties, with a fallback to a default system font.
    font_prop = get_font_properties(font_path)
    print(f"Using font: {font_prop.get_name()}")

    # Setup the coordinate transformer.
    try:
        print(f"Using Source CRS: {source_crs} and Target CRS: {TARGET_CRS}")
        transformer = pyproj.Transformer.from_crs(source_crs, TARGET_CRS, always_xy=True)
    except pyproj.exceptions.CRSError as e:
        print(f"Error initializing CRS transformer: {e}")
        return
        
    all_features = []
    
    def process_entity(entity, transformer, font_prop, exclude_strings):
        """Helper to dispatch entities to the correct processing function."""
        if isinstance(entity, Text):
            features = transform_text_entity(entity, transformer, font_prop, exclude_strings)
        elif isinstance(entity, MText):
            features = transform_mtext_entity(entity, transformer, font_prop, exclude_strings)
        else:
            return # Not a text entity

        if features:
            all_features.extend(features)
            text_preview = entity.dxf.text[:30].strip() if hasattr(entity.dxf, 'text') else entity.plain_text()[:30].strip()
            print(f"  Processed {entity.dxftype()} '{text_preview}...' -> {len(features)} features")

    # --- Entity Processing Loop ---
    # Process all TEXT, MTEXT, and INSERT entities in the modelspace.
    print("\n--- Searching for text entities (including in blocks) ---")
    query = "TEXT MTEXT INSERT"
    entities_to_process = list(msp.query(query))
    
    if not entities_to_process:
        print("No TEXT, MTEXT, or INSERT entities found in the modelspace.")
        return

    for entity in entities_to_process:
        if entity.dxftype() == 'INSERT':
            try:
                # Explode the block reference to get its sub-entities with transformations applied.
                for sub_entity in entity.explode():
                    process_entity(sub_entity, transformer, font_prop, exclude_strings)
            except (ezdxf.DXFStructureError, RecursionError) as e:
                print(f"Warning: Could not explode INSERT entity on layer '{entity.dxf.layer}': {e}")
        else:
            # Process top-level TEXT or MTEXT entities.
            process_entity(entity, transformer, font_prop, exclude_strings)

    # --- File Output ---
    feature_collection = FeatureCollection(all_features)
    print(f"\nTotal characters vectorized: {len(all_features)}")
    
    if not all_features:
        print("Warning: No text was converted. The output file will be empty.")

    try:
        with open(geojson_path, 'w') as f:
            dump(feature_collection, f, indent=2)
        print(f"Successfully created GeoJSON file at: {geojson_path}")
    except IOError as e:
        print(f"Error writing to file '{geojson_path}': {e}")


# --- Main Execution ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Convert DXF text entities (including in blocks) to vector GeoJSON character outlines.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--input", required=True, help="Input DXF file path.")
    parser.add_argument("--output", required=True, help="Output GeoJSON file path.")
    parser.add_argument("--font", required=True, help="Path to the .ttf font file to use for rendering all text.\n(e.g., 'C:/Windows/Fonts/arial.ttf')")
    parser.add_argument("--source_crs", default="EPSG:4326", help="Source CRS of the DXF file (e.g., 'EPSG:27700').\nDefaults to 'EPSG:4326'.")
    parser.add_argument("--exclude_strings", nargs='*', default=['0', '0.0'], help="A space-separated list of strings to exclude from processing.\n(default: ['0', '0.0'])")
    
    args = parser.parse_args()

    # Run the conversion process
    dxf_to_geojson(args.input, args.output, args.font, args.source_crs, args.exclude_strings)
