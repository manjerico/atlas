"""SQLite persistence for the Phase 1 workspace foundation."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def now_iso():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ProjectRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)

    @contextmanager
    def connection(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS base_parcels (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL UNIQUE,
                    geometry_geojson TEXT NOT NULL, bounding_box_json TEXT NOT NULL,
                    crs TEXT NOT NULL, terrain_source_ref TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS project_objects (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    type TEXT NOT NULL, name TEXT NOT NULL,
                    geometry_geojson TEXT NOT NULL, parameters_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS scenarios (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS scenario_objects (
                    id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL,
                    original_object_id TEXT, type TEXT NOT NULL, name TEXT NOT NULL,
                    geometry_geojson TEXT NOT NULL, parameters_json TEXT NOT NULL,
                    snapshot_version INTEGER NOT NULL, snapshot_updated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE,
                    FOREIGN KEY(original_object_id) REFERENCES project_objects(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS simulation_results (
                    id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, scenario_object_id TEXT NOT NULL,
                    engine_type TEXT NOT NULL, parameters_used_json TEXT NOT NULL, status TEXT NOT NULL,
                    metrics_json TEXT NOT NULL, derived_geometries_json TEXT NOT NULL,
                    warnings_json TEXT NOT NULL, errors_json TEXT NOT NULL, limitations_json TEXT NOT NULL,
                    computation_time_ms INTEGER NOT NULL, computed_at TEXT NOT NULL,
                    UNIQUE(scenario_object_id, engine_type),
                    FOREIGN KEY(scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE,
                    FOREIGN KEY(scenario_object_id) REFERENCES scenario_objects(id) ON DELETE CASCADE
                );
                """
            )

    @staticmethod
    def _decode_project(row):
        return dict(row) if row else None

    @staticmethod
    def _decode_parcel(row):
        if not row:
            return None
        result = dict(row)
        result["geometry"] = json.loads(result.pop("geometry_geojson"))
        result["bounding_box"] = json.loads(result.pop("bounding_box_json"))
        return result

    @staticmethod
    def _decode_object(row):
        result = dict(row)
        result["geometry"] = json.loads(result.pop("geometry_geojson"))
        result["parameters"] = json.loads(result.pop("parameters_json"))
        return result

    @classmethod
    def _decode_scenario_object(cls, row):
        return cls._decode_object(row)

    @staticmethod
    def _decode_result(row):
        result = dict(row)
        for name in ("parameters_used", "metrics", "derived_geometries", "warnings", "errors", "limitations"):
            result[name] = json.loads(result.pop(f"{name}_json"))
        return result

    def list_projects(self):
        with self.connection() as connection:
            return [self._decode_project(row) for row in connection.execute("SELECT * FROM projects ORDER BY updated_at DESC")]

    def get_project(self, project_id):
        with self.connection() as connection:
            project = self._decode_project(connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())
            if project:
                project["base_parcel"] = self._decode_parcel(connection.execute("SELECT * FROM base_parcels WHERE project_id = ?", (project_id,)).fetchone())
            return project

    def create_project(self, name, base_parcel):
        project_id, parcel_id, timestamp = str(uuid4()), str(uuid4()), now_iso()
        with self.connection() as connection:
            connection.execute("INSERT INTO projects VALUES (?, ?, ?, ?)", (project_id, name, timestamp, timestamp))
            connection.execute(
                "INSERT INTO base_parcels VALUES (?, ?, ?, ?, ?, ?, ?)",
                (parcel_id, project_id, json.dumps(base_parcel["geometry"]), json.dumps(base_parcel["bounding_box"]), base_parcel["crs"], base_parcel.get("terrain_source_ref"), timestamp),
            )
        return self.get_project(project_id)

    def update_project(self, project_id, name):
        with self.connection() as connection:
            cursor = connection.execute("UPDATE projects SET name = ?, updated_at = ? WHERE id = ?", (name, now_iso(), project_id))
            if cursor.rowcount == 0:
                return None
        return self.get_project(project_id)

    def delete_project(self, project_id):
        with self.connection() as connection:
            return connection.execute("DELETE FROM projects WHERE id = ?", (project_id,)).rowcount > 0

    def list_objects(self, project_id):
        with self.connection() as connection:
            return [self._decode_object(row) for row in connection.execute("SELECT * FROM project_objects WHERE project_id = ? ORDER BY created_at", (project_id,))]

    def get_object(self, project_id, object_id):
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM project_objects WHERE project_id = ? AND id = ?", (project_id, object_id)).fetchone()
            return self._decode_object(row) if row else None

    def create_object(self, project_id, object_data):
        object_id, timestamp = str(uuid4()), now_iso()
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO project_objects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (object_id, project_id, object_data["type"], object_data["name"], json.dumps(object_data["geometry"]), json.dumps(object_data["parameters"]), timestamp, timestamp),
            )
        return self.get_object(project_id, object_id)

    def update_object(self, project_id, object_id, object_data):
        with self.connection() as connection:
            cursor = connection.execute(
                """UPDATE project_objects
                   SET type = ?, name = ?, geometry_geojson = ?, parameters_json = ?, updated_at = ?
                   WHERE project_id = ? AND id = ?""",
                (object_data["type"], object_data["name"], json.dumps(object_data["geometry"]), json.dumps(object_data["parameters"]), now_iso(), project_id, object_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_object(project_id, object_id)

    def delete_object(self, project_id, object_id):
        with self.connection() as connection:
            return connection.execute("DELETE FROM project_objects WHERE project_id = ? AND id = ?", (project_id, object_id)).rowcount > 0

    def create_scenario(self, project_id, name):
        scenario_id, timestamp = str(uuid4()), now_iso()
        with self.connection() as connection:
            connection.execute("INSERT INTO scenarios VALUES (?, ?, ?, ?, ?)", (scenario_id, project_id, name, timestamp, timestamp))
            objects = connection.execute("SELECT * FROM project_objects WHERE project_id = ?", (project_id,)).fetchall()
            for object_row in objects:
                connection.execute(
                    "INSERT INTO scenario_objects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid4()), scenario_id, object_row["id"], object_row["type"], object_row["name"], object_row["geometry_geojson"], object_row["parameters_json"], 1, timestamp, timestamp),
                )
        return self.get_scenario(project_id, scenario_id)

    def list_scenarios(self, project_id):
        with self.connection() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM scenarios WHERE project_id = ? ORDER BY created_at", (project_id,))]

    def get_scenario(self, project_id, scenario_id):
        with self.connection() as connection:
            scenario = connection.execute("SELECT * FROM scenarios WHERE project_id = ? AND id = ?", (project_id, scenario_id)).fetchone()
            if not scenario:
                return None
            result = dict(scenario)
            rows = connection.execute("SELECT * FROM scenario_objects WHERE scenario_id = ? ORDER BY created_at", (scenario_id,)).fetchall()
            result["objects"] = [self._decode_scenario_object(row) for row in rows]
            return result

    def get_scenario_object(self, scenario_id, scenario_object_id):
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM scenario_objects WHERE scenario_id = ? AND id = ?", (scenario_id, scenario_object_id)).fetchone()
            return self._decode_scenario_object(row) if row else None

    def update_scenario(self, project_id, scenario_id, name):
        with self.connection() as connection:
            cursor = connection.execute("UPDATE scenarios SET name = ?, updated_at = ? WHERE project_id = ? AND id = ?", (name, now_iso(), project_id, scenario_id))
            if cursor.rowcount == 0:
                return None
        return self.get_scenario(project_id, scenario_id)

    def delete_scenario(self, project_id, scenario_id):
        with self.connection() as connection:
            return connection.execute("DELETE FROM scenarios WHERE project_id = ? AND id = ?", (project_id, scenario_id)).rowcount > 0

    def duplicate_scenario(self, project_id, scenario_id, name):
        source = self.get_scenario(project_id, scenario_id)
        if not source:
            return None
        duplicate_id, timestamp = str(uuid4()), now_iso()
        with self.connection() as connection:
            connection.execute("INSERT INTO scenarios VALUES (?, ?, ?, ?, ?)", (duplicate_id, project_id, name, timestamp, timestamp))
            for object_data in source["objects"]:
                connection.execute(
                    "INSERT INTO scenario_objects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid4()), duplicate_id, object_data["original_object_id"], object_data["type"], object_data["name"], json.dumps(object_data["geometry"]), json.dumps(object_data["parameters"]), object_data["snapshot_version"], object_data["snapshot_updated_at"], timestamp),
                )
        return self.get_scenario(project_id, duplicate_id)

    def update_scenario_object(self, scenario_id, scenario_object_id, object_data):
        timestamp = now_iso()
        with self.connection() as connection:
            cursor = connection.execute(
                """UPDATE scenario_objects SET type = ?, name = ?, geometry_geojson = ?, parameters_json = ?, snapshot_updated_at = ?
                   WHERE scenario_id = ? AND id = ?""",
                (object_data["type"], object_data["name"], json.dumps(object_data["geometry"]), json.dumps(object_data["parameters"]), timestamp, scenario_id, scenario_object_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_scenario_object(scenario_id, scenario_object_id)

    def create_scenario_object(self, scenario_id, object_data):
        object_id, timestamp = str(uuid4()), now_iso()
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO scenario_objects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (object_id, scenario_id, None, object_data["type"], object_data["name"], json.dumps(object_data["geometry"]), json.dumps(object_data["parameters"]), 1, timestamp, timestamp),
            )
        return self.get_scenario_object(scenario_id, object_id)

    def delete_scenario_object(self, scenario_id, scenario_object_id):
        with self.connection() as connection:
            return connection.execute("DELETE FROM scenario_objects WHERE scenario_id = ? AND id = ?", (scenario_id, scenario_object_id)).rowcount > 0

    def update_scenario_object_from_project(self, project_id, scenario_id, scenario_object_id):
        timestamp = now_iso()
        with self.connection() as connection:
            scenario_object = connection.execute("SELECT * FROM scenario_objects WHERE scenario_id = ? AND id = ?", (scenario_id, scenario_object_id)).fetchone()
            if not scenario_object or scenario_object["original_object_id"] is None:
                return None
            source = connection.execute("SELECT * FROM project_objects WHERE project_id = ? AND id = ?", (project_id, scenario_object["original_object_id"])).fetchone()
            if not source:
                return None
            connection.execute(
                """UPDATE scenario_objects SET type = ?, name = ?, geometry_geojson = ?, parameters_json = ?,
                   snapshot_version = snapshot_version + 1, snapshot_updated_at = ? WHERE id = ?""",
                (source["type"], source["name"], source["geometry_geojson"], source["parameters_json"], timestamp, scenario_object_id),
            )
        return self.get_scenario_object(scenario_id, scenario_object_id)

    def list_simulation_results(self, scenario_id):
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM simulation_results WHERE scenario_id = ? ORDER BY computed_at DESC", (scenario_id,)).fetchall()
            results = []
            for row in rows:
                result = self._decode_result(row)
                snapshot = connection.execute("SELECT snapshot_updated_at FROM scenario_objects WHERE id = ?", (result["scenario_object_id"],)).fetchone()
                result["is_stale"] = bool(snapshot and snapshot["snapshot_updated_at"] > result["computed_at"])
                results.append(result)
            return results

    def replace_simulation_result(self, scenario_id, scenario_object_id, engine_type, result):
        result_id, timestamp = str(uuid4()), now_iso()
        with self.connection() as connection:
            connection.execute("DELETE FROM simulation_results WHERE scenario_object_id = ? AND engine_type = ?", (scenario_object_id, engine_type))
            connection.execute(
                "INSERT INTO simulation_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (result_id, scenario_id, scenario_object_id, engine_type, json.dumps(result["parameters_used"]), result["status"], json.dumps(result["metrics"]), json.dumps(result["derived_geometries"]), json.dumps(result["warnings"]), json.dumps(result["errors"]), json.dumps(result["limitations"]), result["computation_time_ms"], timestamp),
            )
            row = connection.execute("SELECT * FROM simulation_results WHERE id = ?", (result_id,)).fetchone()
            return self._decode_result(row)
