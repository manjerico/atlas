"""Lazy, project-session-scoped access to the V1 LiDAR terrain source."""

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
        key = (min_row, max_row, min_col, max_col)
        if key in self._cache:
            return self._cache[key]
        if min_row < 0 or min_col < 0 or max_col >= self._tiles[0]["shape"][1] or max_row < min_row or max_col < min_col:
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
