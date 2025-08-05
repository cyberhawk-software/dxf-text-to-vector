# -*- coding: utf-8 -*-
#
# Author: Vitalij L. (vitalij.lokucijevskij@thecyberhawk.com)
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
from ezdxf.math import OCS
from shapely.geometry import Polygon, mapping
from geojson import Feature, FeatureCollection, dump
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties

# --- Configuration ---

# Set the target CRS for the GeoJSON output.
# WGS84 is the standard for most web mapping applications.
TARGET_CRS = "EPSG:4326"  # WGS84

# --- Helper Functions ---

def create_char_path(char: str, font_path: str, size: float = 1.0) -> TextPath:
    """
    Creates a matplotlib TextPath object for a single character.
    """
    # Use FontProperties with the fname parameter to specify a direct file path.
    # This correctly handles paths with special characters like '-' and avoids
    # parsing the path as a font family name.
    try:
        font_prop = FontProperties(fname=font_path)
        return TextPath((0, 0), char, size=size, prop=font_prop)
    except Exception as e:
        print(f"Warning: Could not create text path for character '{char}' with font {font_path}. Error: {e}")
        return None


def transform_text_entity(entity: Text, transformer: pyproj.Transformer, font_path: str) -> list[Feature]:
    """
    Processes a single TEXT entity.
    """
    features = []
    doc = entity.doc
    if not doc:
        return []

    # Get text properties
    text_string = entity.dxf.text
    insert_point = np.array(entity.dxf.insert)
    height = entity.dxf.height
    rotation = entity.dxf.rotation  # in degrees
    layer = entity.dxf.layer
    
    # We use the user-provided font for all text entities.
    font_name = os.path.basename(font_path)

    # OCS transformation
    ocs = entity.ocs()
    
    current_pos = np.copy(insert_point)

    for char in text_string:
        if char.isspace():
            # Simple space handling: advance position based on a fraction of height
            space_width = height * 0.5 
            advance = np.array([space_width, 0, 0])
            rad = np.deg2rad(rotation)
            rot_matrix = np.array([
                [np.cos(rad), -np.sin(rad), 0],
                [np.sin(rad), np.cos(rad), 0],
                [0, 0, 1]
            ])
            current_pos += advance @ rot_matrix.T[:3,:3]
            continue

        char_path = create_char_path(char, font_path, size=height)
        if char_path is None:
            continue
        
        try:
            char_bbox = char_path.get_extents()
            char_width = char_bbox.width
        except Exception:
            char_width = height * 0.5 # Fallback

        transformed_verts = []
        for point in char_path.vertices:
            vec = np.array([point[0], point[1], 0])
            
            rad = np.deg2rad(rotation)
            rot_matrix = np.array([
                [np.cos(rad), -np.sin(rad), 0],
                [np.sin(rad), np.cos(rad), 0],
                [0, 0, 1]
            ])
            rotated_vec = vec @ rot_matrix.T[:3, :3]
            
            final_vec_ocs = current_pos + rotated_vec
            final_vec_wcs = ocs.to_wcs(final_vec_ocs)
            
            lon, lat = transformer.transform(final_vec_wcs[0], final_vec_wcs[1])
            transformed_verts.append((lon, lat))

        if not transformed_verts or len(transformed_verts) < 3:
            continue

        polygon = Polygon(transformed_verts)
        feature = Feature(
            geometry=mapping(polygon),
            properties={
                "text": text_string,
                "char": char,
                "layer": layer,
                "font": font_name,
                "insert_x_wcs": float(insert_point[0]),
                "insert_y_wcs": float(insert_point[1]),
            }
        )
        features.append(feature)
        
        advance = np.array([char_width, 0, 0])
        rad = np.deg2rad(rotation)
        rot_matrix = np.array([
            [np.cos(rad), -np.sin(rad), 0],
            [np.sin(rad), np.cos(rad), 0],
            [0, 0, 1]
        ])
        current_pos += advance @ rot_matrix.T[:3,:3]
        
    return features


def transform_mtext_entity(entity: MText, transformer: pyproj.Transformer, font_path: str) -> list[Feature]:
    """
    Processes a single MTEXT entity.
    """
    all_features = []
    
    # MTEXT provides a method to iterate through its content fragments
    for fragment in entity.fragments():
        # Each fragment has properties like text, font, height, etc.
        line_pseudo_text = Text.new(dxfattribs={
            'text': fragment.text,
            'insert': fragment.insert,
            'height': fragment.height,
            'rotation': fragment.rotation,
            'layer': entity.dxf.layer,
            'style': entity.dxf.style,
        })
        line_pseudo_text.doc = entity.doc
        # The fragment insert point is already in WCS
        line_pseudo_text.set_ocs(OCS()) 
        
        all_features.extend(transform_text_entity(line_pseudo_text, transformer, font_path))
        
    return all_features


def dxf_to_geojson(dxf_path: str, geojson_path: str, font_path: str, source_crs: str, exclude_strings: list[str] = None) -> None:
    """
    Main function to convert DXF TEXT/MTEXT to GeoJSON feature outlines.
    This function now handles TEXT/MTEXT inside block references (INSERT entities).
    """
    print(f"Loading DXF file: {dxf_path}")
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except IOError:
        print(f"Error: Cannot open DXF file at '{dxf_path}'.")
        return
    except ezdxf.DXFStructureError as e:
        print(f"Error: Invalid or corrupt DXF file. {e}")
        return

    if not os.path.exists(font_path):
        print(f"Error: Font file not found at '{font_path}'")
        return

    try:
        print(f"Using Source CRS: {source_crs} and Target CRS: {TARGET_CRS}")
        transformer = pyproj.Transformer.from_crs(source_crs, TARGET_CRS, always_xy=True)
    except pyproj.exceptions.CRSError as e:
        print(f"Error: Invalid CRS specified. {e}")
        print(f"Please check source_crs ('{source_crs}') and TARGET_CRS ('{TARGET_CRS}').")
        return
        
    all_features = []
    
    def process_entity(entity, transformer, font_path, exclude_strings=None):
        """Helper to process a single entity, whether it's Text or MText."""
        """Exclude empty or non-text entities."""
        if not entity or not isinstance(entity, (Text, MText)):
            return
        if not entity.dxf.text and not isinstance(entity, MText):
            return
        """Exclude 0 and 0.0 TEXT and MTEXT entities."""
        if exclude_strings is None:
            exclude_strings = []
        if (isinstance(entity, Text) or isinstance(entity, MText)) and (entity.dxf.text in exclude_strings):
            return

        if isinstance(entity, Text):
            features = transform_text_entity(entity, transformer, font_path)
            if features:
                all_features.extend(features)
                print(f"  Processed TEXT '{entity.dxf.text[:30].strip()}' -> {len(features)} features")
        elif isinstance(entity, MText):
            features = transform_mtext_entity(entity, transformer, font_path)
            if features:
                all_features.extend(features)
                print(f"  Processed MTEXT at ({entity.dxf.insert.x:.2f}, {entity.dxf.insert.y:.2f}) -> {len(features)} features")

    # 1. Process top-level TEXT and MTEXT entities in modelspace
    print("\n--- Searching for top-level entities ---")
    top_level_entities = list(msp.query('TEXT MTEXT'))
    if top_level_entities:
        print(f"Found {len(top_level_entities)} top-level TEXT/MTEXT entities.")
        for entity in top_level_entities:
            process_entity(entity, transformer, font_path, exclude_strings)
    else:
        print("No top-level TEXT or MTEXT entities found.")

    # 2. Process TEXT and MTEXT inside block references (INSERT entities)
    print("\n--- Searching for entities inside block references (INSERTs) ---")
    insert_entities = msp.query('INSERT')
    if insert_entities:
        print(f"Found {len(insert_entities)} INSERT entities. Exploding them to find text...")
        for insert_entity in insert_entities:
            try:
                # Explode the block reference, which yields sub-entities with transformations applied
                for sub_entity in insert_entity.explode():
                    process_entity(sub_entity, transformer, font_path, exclude_strings)
            except (ezdxf.DXFStructureError, RecursionError) as e:
                print(f"Could not explode INSERT entity on layer '{insert_entity.dxf.layer}': {e}")
    else:
        print("No INSERT entities found.")

    feature_collection = FeatureCollection(all_features)
    
    print(f"\nTotal characters vectorized: {len(all_features)}")
    
    if len(all_features) == 0:
        print("Warning: No text was found to convert. The output file will be empty.")

    try:
        with open(geojson_path, 'w') as f:
            dump(feature_collection, f, indent=2)
        print(f"Successfully created GeoJSON file at: {geojson_path}")
    except IOError:
        print(f"Error: Could not write to file at '{geojson_path}'.")


# --- Main Execution ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Convert DXF text/mtext entities (including in blocks) to vector GeoJSON character outlines."
    )
    parser.add_argument("--input", required=True, help="Input DXF file path.")
    parser.add_argument("--output", required=True, help="Output GeoJSON file path.")
    parser.add_argument("--font", required=True, help="Path to the .ttf font file to use for rendering all text (e.g., C:/Windows/Fonts/arial.ttf).")
    parser.add_argument("--source_crs", default="EPSG:4326", help="Source CRS of the DXF file (e.g., 'EPSG:27700'). Defaults to EPSG:4326'.")
    parser.add_argument("--exclude_strings", nargs='*', default=['0', '0.0'], help="Strings to exclude from processing (default: ['0', '0.0']).")
    
    args = parser.parse_args()

    # Run the conversion process
    dxf_to_geojson(args.input, args.output, args.font, args.source_crs, args.exclude_strings)
