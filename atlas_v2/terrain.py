"""Lazy, project-session-scoped access to the V1 LiDAR terrain source."""

import math
from pathlib import Path

import numpy as np
import tifffile

from motor_charca import en_para_latlon, latlon_para_en


class TerrainClip:
    """A Mosaico-compatible clipped grid for unmodified V1 terrain engines."""

    def __init__(self, grid, origin_x, origin_y, pixel):
        self.grid = grid
        self.origem_x = origin_x
        self.origem_y = origin_y
        self.pixel = pixel

    def latlon_para_pixel(self, lat, lon):
        east, north = latlon_para_en(lat, lon)
        return round((self.origem_y - north) / self.pixel), round((east - self.origem_x) / self.pixel)

    def pixel_para_latlon(self, row, col):
        return en_para_latlon(self.origem_x + col * self.pixel, self.origem_y - row * self.pixel)

    def dentro(self, row, col):
        return 0 <= row < self.grid.shape[0] and 0 <= col < self.grid.shape[1]


class TerrainContext:
    """Loads only requested LiDAR windows and caches them for one project session."""

    def __init__(self, project_id, north_path, south_path):
        self.project_id = project_id
        self._tiles = self._load_metadata([north_path, south_path])
        self.pixel = self._tiles[0]["pixel"]
        self.origin_x = self._tiles[0]["origin_x"]
        self.origin_y = self._tiles[0]["origin_y"]
        self.total_rows = sum(tile["shape"][0] for tile in self._tiles)
        self.total_cols = self._tiles[0]["shape"][1]
        self._cache = {}

    @staticmethod
    def _load_metadata(paths):
        tiles = []
        for path in paths:
            path = Path(path)
            if not path.is_file():
                raise FileNotFoundError(f"MDT não encontrado: {path}")
            with tifffile.TiffFile(path) as source:
                page = source.pages[0]
                tags = {tag.name: tag.value for tag in page.tags.values()}
                scale, tiepoint = tags["ModelPixelScaleTag"], tags["ModelTiepointTag"]
                tiles.append({"path": path, "shape": page.shape, "pixel": float(scale[0]), "origin_x": float(tiepoint[3]), "origin_y": float(tiepoint[4])})
        tiles.sort(key=lambda tile: tile["origin_y"], reverse=True)
        if len({tile["pixel"] for tile in tiles}) != 1 or len({tile["origin_x"] for tile in tiles}) != 1:
            raise ValueError("Os MDT têm de partilhar origem X e resolução para formar o mosaico.")
        row_offset = 0
        for tile in tiles:
            tile["global_row_start"] = row_offset
            row_offset += tile["shape"][0]
        return tiles

    def _global_pixel(self, lat, lon):
        east, north = latlon_para_en(lat, lon)
        return round((self.origin_y - north) / self.pixel), round((east - self.origin_x) / self.pixel)

    def fill_cache(self, bounds):
        """Return a clipped TerrainClip for (min_row, max_row, min_col, max_col)."""
        min_row, max_row, min_col, max_col = bounds
        min_row = max(0, min_row)
        min_col = max(0, min_col)
        max_row = min(self.total_rows - 1, max_row)
        max_col = min(self.total_cols - 1, max_col)
        key = (min_row, max_row, min_col, max_col)
        if key in self._cache:
            return self._cache[key]
        if max_row < min_row or max_col < min_col:
            raise ValueError("A geometria está fora da cobertura do MDT.")
        parts = []
        for tile in self._tiles:
            start, end = tile["global_row_start"], tile["global_row_start"] + tile["shape"][0] - 1
            if max_row < start or min_row > end:
                continue
            local_start, local_end = max(min_row, start) - start, min(max_row, end) - start
            # memmap avoids materialising an entire GeoTIFF; only this slice is copied.
            grid = tifffile.memmap(tile["path"])
            parts.append(np.asarray(grid[local_start:local_end + 1, min_col:max_col + 1], dtype=np.float32))
        if not parts:
            raise ValueError("A geometria está fora da cobertura do MDT.")
        clip = TerrainClip(np.vstack(parts), self.origin_x + min_col * self.pixel, self.origin_y - min_row * self.pixel, self.pixel)
        self._cache[key] = clip
        return clip

    def clip_for_geojson(self, geometry, padding_pixels=2):
        points = geometry["coordinates"][0]
        rows_cols = [self._global_pixel(lat=point[1], lon=point[0]) for point in points]
        rows, cols = zip(*rows_cols)
        return self.fill_cache((max(0, min(rows) - padding_pixels), max(rows) + padding_pixels, max(0, min(cols) - padding_pixels), max(cols) + padding_pixels))

    @staticmethod
    def _coordinate_pairs(value):
        """Yield coordinate pairs from any supported GeoJSON nesting level."""
        if (
            isinstance(value, (list, tuple))
            and len(value) >= 2
            and all(isinstance(number, (int, float)) for number in value[:2])
        ):
            yield value[0], value[1]
            return
        if isinstance(value, (list, tuple)):
            for child in value:
                yield from TerrainContext._coordinate_pairs(child)

    def mesh_for_geometries(self, geometries, max_dimension=180, padding_pixels=8):
        """Create a bounded project terrain mesh without loading the full mosaic."""
        points = [
            point
            for geometry in geometries
            for point in self._coordinate_pairs(geometry.get("coordinates", []))
        ]
        if not points:
            raise ValueError("Não existem coordenadas para recortar o terreno.")

        requested = [self._global_pixel(lat=lat, lon=lon) for lon, lat in points]
        rows, cols = zip(*requested)
        requested_bounds = (
            min(rows) - padding_pixels,
            max(rows) + padding_pixels,
            min(cols) - padding_pixels,
            max(cols) + padding_pixels,
        )
        coverage_complete = (
            requested_bounds[0] >= 0
            and requested_bounds[1] < self.total_rows
            and requested_bounds[2] >= 0
            and requested_bounds[3] < self.total_cols
        )
        clip = self.fill_cache(requested_bounds)
        height, width = clip.grid.shape
        reduction = max(1, math.ceil(max(height, width) / max_dimension))
        reduced = clip.grid[::reduction, ::reduction]
        rows_reduced, cols_reduced = reduced.shape
        pixel_m = clip.pixel * reduction

        return {
            "n_linhas": rows_reduced,
            "n_cols": cols_reduced,
            "pixel_m": pixel_m,
            "elevacoes": reduced.round(2).tolist(),
            "elevacao_min": float(reduced.min()),
            "elevacao_max": float(reduced.max()),
            "sample_reduction": reduction,
            "coverage_complete": coverage_complete,
            "origin_east": clip.origem_x,
            "origin_north": clip.origem_y,
            "bbox_3763": {
                # The V1 terrain uses TM06 without the official false offsets.
                # A standards-compliant EPSG:3763 representation requires them.
                "xmin": clip.origem_x + 200000.0,
                "xmax": clip.origem_x + (cols_reduced - 1) * pixel_m + 200000.0,
                "ymin": clip.origem_y - (rows_reduced - 1) * pixel_m + 300000.0,
                "ymax": clip.origem_y + 300000.0,
            },
            "orthophoto_bbox": {
                # The Silves ORTOS2023 service declares EPSG:3763 but publishes
                # its extent without the official false easting/northing.
                "xmin": clip.origem_x,
                "xmax": clip.origem_x + (cols_reduced - 1) * pixel_m,
                "ymin": clip.origem_y - (rows_reduced - 1) * pixel_m,
                "ymax": clip.origem_y,
            },
            "source": {
                "label": "MDT LiDAR 2 m",
                "native_resolution_m": clip.pixel,
                "display_resolution_m": pixel_m,
                "coverage_complete": coverage_complete,
                "limitations": [
                    "Modelo adequado a estudo preliminar; não substitui levantamento topográfico.",
                    "A resolução apresentada pode ser reduzida para manter a navegação 3D fluida.",
                ],
            },
            "_clip": clip,
        }

    def project_geojson(self, geometry, clip):
        """Project GeoJSON paths into the local metre-based terrain frame."""
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates", [])
        if geometry_type == "Polygon":
            paths = coordinates
        elif geometry_type == "MultiPolygon":
            paths = [ring for polygon in coordinates for ring in polygon]
        elif geometry_type == "LineString":
            paths = [coordinates]
        elif geometry_type == "MultiLineString":
            paths = coordinates
        else:
            return {"type": geometry_type, "paths": []}

        projected_paths = []
        for path in paths:
            projected = []
            for lon, lat in path:
                east, north = latlon_para_en(lat, lon)
                row = round((clip.origem_y - north) / clip.pixel)
                col = round((east - clip.origem_x) / clip.pixel)
                elevation = None
                if clip.dentro(row, col):
                    elevation = float(clip.grid[row, col])
                projected.append({
                    "x": float(east - clip.origem_x),
                    "z": float(clip.origem_y - north),
                    "elevation": elevation,
                })
            projected_paths.append(projected)
        return {"type": geometry_type, "paths": projected_paths}
