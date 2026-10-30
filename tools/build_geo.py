#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export a small, clipped Natural Earth basemap for the /tc/ page."""

from __future__ import annotations

import json
from pathlib import Path

import shapefile
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon, box, shape

BASE_DIR = Path(__file__).resolve().parents[1]
NE = BASE_DIR / ".cartopy" / "shapefiles" / "natural_earth"
OUT = BASE_DIR / "public" / "tc-data" / "geo.json"
BBOX = box(99.2, 8.8, 140.8, 36.2)


def coords_ring(ring, ndigits=3):
    return [[round(x, ndigits), round(y, ndigits)] for x, y in ring]


def polygon_rings(geom):
    polygons = []
    if isinstance(geom, Polygon):
        polygons = [geom]
    elif isinstance(geom, MultiPolygon):
        polygons = list(geom.geoms)
    rings = []
    for poly in polygons:
        if poly.area < 0.002:
            continue
        outer = coords_ring(poly.exterior.coords)
        if len(outer) >= 4:
            rings.append(outer)
    return rings


def line_parts(geom):
    parts = []
    if isinstance(geom, LineString):
        parts = [geom]
    elif isinstance(geom, MultiLineString):
        parts = list(geom.geoms)
    out = []
    for line in parts:
        if line.length < 0.02:
            continue
        coords = coords_ring(line.coords)
        if len(coords) >= 2:
            out.append(coords)
    return out


def load_land():
    reader = shapefile.Reader(str(NE / "physical" / "ne_50m_land.shp"))
    rings = []
    for shp in reader.shapes():
        geom = shape(shp.__geo_interface__)
        if not geom.intersects(BBOX):
            continue
        clipped = geom.intersection(BBOX).simplify(0.015, preserve_topology=True)
        rings.extend(polygon_rings(clipped))
    return rings


def load_lines(name, tolerance=0.012):
    reader = shapefile.Reader(str(NE / "cultural" / name))
    parts = []
    for shp in reader.shapes():
        geom = shape(shp.__geo_interface__)
        if not geom.intersects(BBOX):
            continue
        clipped = geom.intersection(BBOX).simplify(tolerance, preserve_topology=True)
        parts.extend(line_parts(clipped))
    return parts


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    land = load_land()
    borders = load_lines("ne_50m_admin_0_boundary_lines_land.shp")
    data = {
        "bbox": [99.2, 8.8, 140.8, 36.2],
        "land": land,
        "borders": borders,
        "source": "Natural Earth 1:50m (public domain)",
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("land rings", len(land), "border parts", len(borders), "bytes", OUT.stat().st_size)


if __name__ == "__main__":
    main()
