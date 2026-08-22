import os
import importlib
import sys
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


class WorkspaceApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "atlas.sqlite3")
        os.environ["ATLAS_V2_DATABASE"] = self.database_path
        sys.modules.pop("app", None)
        app = importlib.import_module("app")
        self.client = app.app.test_client()
        self.base_parcel = {
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
            },
            "crs": "EPSG:4326",
            "terrain_source_ref": "test",
        }

    def tearDown(self):
        self.temp_dir.cleanup()
        os.environ.pop("ATLAS_V2_DATABASE", None)

    def create_project(self):
        response = self.client.post("/api/v2/projects", json={"name": "Quinta", "base_parcel": self.base_parcel})
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def test_project_is_created_with_immutable_base_parcel(self):
        project = self.create_project()
        self.assertEqual(project["name"], "Quinta")
        self.assertEqual(project["base_parcel"]["crs"], "EPSG:4326")
        self.assertEqual(project["base_parcel"]["bounding_box"], {"min_x": 0, "min_y": 0, "max_x": 10, "max_y": 10})
        updated = self.client.put(f"/api/v2/projects/{project['id']}", json={"name": "Quinta Nova"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["base_parcel"]["id"], project["base_parcel"]["id"])
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/api/motor-solar").status_code, 400)

    def test_object_crud_and_containment_warning(self):
        project = self.create_project()
        geometry = {"type": "Polygon", "coordinates": [[[1, 1], [12, 1], [1, 3], [1, 1]]]}
        created = self.client.post(
            f"/api/v2/projects/{project['id']}/objects",
            json={"type": "zone", "name": "Zona parcial", "geometry": geometry, "parameters": {}},
        )
        self.assertEqual(created.status_code, 201)
        body = created.get_json()
        self.assertEqual(len(body["warnings"]), 1)
        object_id = body["object"]["id"]
        listed = self.client.get(f"/api/v2/projects/{project['id']}/objects").get_json()["objects"]
        self.assertEqual([item["id"] for item in listed], [object_id])
        updated = self.client.put(
            f"/api/v2/projects/{project['id']}/objects/{object_id}",
            json={"type": "zone", "name": "Zona revista", "geometry": geometry, "parameters": {}},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["object"]["name"], "Zona revista")
        deleted = self.client.delete(f"/api/v2/projects/{project['id']}/objects/{object_id}")
        self.assertEqual(deleted.status_code, 204)

    def test_invalid_or_outside_geometry_is_rejected(self):
        project = self.create_project()
        self_intersecting = {"type": "Polygon", "coordinates": [[[1, 1], [4, 4], [1, 4], [4, 1], [1, 1]]]}
        response = self.client.post(
            f"/api/v2/projects/{project['id']}/objects",
            json={"type": "zone", "name": "Inválida", "geometry": self_intersecting, "parameters": {}},
        )
        self.assertEqual(response.status_code, 400)
        outside = {"type": "Polygon", "coordinates": [[[20, 20], [22, 20], [20, 22], [20, 20]]]}
        response = self.client.post(
            f"/api/v2/projects/{project['id']}/objects",
            json={"type": "zone", "name": "Fora", "geometry": outside, "parameters": {}},
        )
        self.assertEqual(response.status_code, 400)

    def test_type_registry_parameters_are_enforced(self):
        project = self.create_project()
        geometry = {"type": "Polygon", "coordinates": [[[1, 1], [4, 1], [1, 4], [1, 1]]]}
        response = self.client.post(
            f"/api/v2/projects/{project['id']}/objects",
            json={"type": "platform", "name": "Plataforma", "geometry": geometry, "parameters": {"target_elevation": 42.5}},
        )
        self.assertEqual(response.status_code, 400)

    def test_earthwork_runs_against_the_real_mdt(self):
        lat, lon = 37.357448, -8.308065
        parcel = {
            "geometry": {"type": "Polygon", "coordinates": [[[lon - .002, lat - .002], [lon + .002, lat - .002], [lon + .002, lat + .002], [lon - .002, lat + .002], [lon - .002, lat - .002]]]},
            "crs": "EPSG:4326",
        }
        project = self.client.post("/api/v2/projects", json={"name": "MDT", "base_parcel": parcel}).get_json()
        geometry = {"type": "Polygon", "coordinates": [[[lon - .0005, lat - .0005], [lon + .0005, lat - .0005], [lon, lat + .0005], [lon - .0005, lat - .0005]]]}
        object_response = self.client.post(f"/api/v2/projects/{project['id']}/objects", json={"type": "platform", "name": "Plataforma", "geometry": geometry, "parameters": {}})
        self.assertEqual(object_response.status_code, 201)
        scenario = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Teste"}).get_json()
        scenario_object = scenario["objects"][0]
        response = self.client.post("/api/v2/simulations/run", json={"scenario_id": scenario["id"], "scenario_object_id": scenario_object["id"], "engine_type": "earthwork"})
        self.assertEqual(response.status_code, 201)
        result = response.get_json()
        self.assertEqual(result["status"], "success")
        self.assertGreater(result["metrics"]["area_total_m2"], 0)
        self.assertIn("volume_corte_m3", result["metrics"])
        repeat = self.client.post("/api/v2/simulations/run", json={"scenario_id": scenario["id"], "scenario_object_id": scenario_object["id"], "engine_type": "earthwork"})
        self.assertEqual(repeat.status_code, 201)
        database = sqlite3.connect(self.database_path)
        try:
            count = database.execute("SELECT COUNT(*) FROM simulation_results WHERE scenario_object_id = ? AND engine_type = ?", (scenario_object["id"], "earthwork")).fetchone()[0]
        finally:
            database.close()
        self.assertEqual(count, 1)

    def test_cultivable_area_runs_through_the_v1_adapter(self):
        lat, lon = 37.357448, -8.308065
        parcel = {
            "geometry": {"type": "Polygon", "coordinates": [[[lon - .002, lat - .002], [lon + .002, lat - .002], [lon + .002, lat + .002], [lon - .002, lat + .002], [lon - .002, lat - .002]]]},
            "crs": "EPSG:4326",
        }
        project = self.client.post("/api/v2/projects", json={"name": "Cultivo", "base_parcel": parcel}).get_json()
        geometry = {"type": "Polygon", "coordinates": [[[lon - .0005, lat - .0005], [lon + .0005, lat - .0005], [lon, lat + .0005], [lon - .0005, lat - .0005]]]}
        object_response = self.client.post(
            f"/api/v2/projects/{project['id']}/objects",
            json={"type": "crop_area", "name": "Olival", "geometry": geometry, "parameters": {}},
        )
        self.assertEqual(object_response.status_code, 201)
        scenario = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Agrícola"}).get_json()
        scenario_object = scenario["objects"][0]
        with patch("motor_agricultura._query_geometrias", return_value=[]):
            response = self.client.post(
                "/api/v2/simulations/run",
                json={"scenario_id": scenario["id"], "scenario_object_id": scenario_object["id"], "engine_type": "cultivable_area"},
            )
        self.assertEqual(response.status_code, 201)
        result = response.get_json()
        self.assertEqual(result["status"], "success")
        self.assertGreater(result["metrics"]["area_total_ha"], 0)
        self.assertIn("percentagem_cultivavel", result["metrics"])
        self.assertEqual(result["parameters_used"], {})

    def test_type_registry_only_advertises_available_adapters(self):
        from atlas_v2.adapters import ADAPTERS

        registry = self.client.get("/api/v2/types").get_json()
        advertised = {engine for definition in registry.values() for engine in definition["engines"]}
        self.assertTrue(advertised)
        self.assertLessEqual(advertised, set(ADAPTERS))
        self.assertIn("cultivable_area", registry["crop_area"]["engines"])

    def test_building_registry_exposes_configurable_models_and_constraints(self):
        registry = self.client.get("/api/v2/types").get_json()
        building = registry["building"]
        self.assertEqual(set(building["presets"]), {
            "single_storey_house", "two_storey_house", "warehouse", "annex"
        })
        self.assertEqual(building["allowed_geometry_types"], ["Polygon"])
        self.assertTrue(building["parameter_schema"]["model"]["required"])

    def test_guided_building_preview_does_not_persist_objects(self):
        lat, lon = 37.357448, -8.308065
        parcel = {
            "geometry": {"type": "Polygon", "coordinates": [[[lon - .002, lat - .002], [lon + .002, lat - .002], [lon + .002, lat + .002], [lon - .002, lat + .002], [lon - .002, lat - .002]]]},
            "crs": "EPSG:4326",
        }
        project = self.client.post("/api/v2/projects", json={"name": "Assistente", "base_parcel": parcel}).get_json()
        response = self.client.post(
            f"/api/v2/projects/{project['id']}/planning/building-preview",
            json={
                "center": [lon, lat], "model": "single_storey_house",
                "width_m": 10, "length_m": 14, "orientation_degrees": 25,
                "include_platform": True, "include_access": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        preview = response.get_json()
        self.assertEqual([item["role"] for item in preview["objects"]], ["building", "platform", "access"])
        self.assertEqual(preview["summary"]["footprint_area_m2"], 140)
        self.assertGreater(preview["summary"]["access_length_m"], 0)
        self.assertTrue(preview["limitations"])
        scenario = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Alternativa"}).get_json()
        self.assertEqual(scenario["objects"], [])

    def test_guided_building_proposal_persists_generic_objects_and_earthwork(self):
        lat, lon = 37.357448, -8.308065
        parcel = {
            "geometry": {"type": "Polygon", "coordinates": [[[lon - .002, lat - .002], [lon + .002, lat - .002], [lon + .002, lat + .002], [lon - .002, lat + .002], [lon - .002, lat - .002]]]},
            "crs": "EPSG:4326",
        }
        project = self.client.post("/api/v2/projects", json={"name": "Proposta", "base_parcel": parcel}).get_json()
        scenario = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Implantação A"}).get_json()
        response = self.client.post(
            f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}/planning/building-proposal",
            json={
                "center": [lon, lat], "model": "two_storey_house",
                "width_m": 9, "length_m": 11, "floors": 2, "height_m": 6.6,
                "orientation_degrees": 90, "earthwork_tolerance": "balanced",
                "include_platform": True, "include_access": True,
            },
        )
        self.assertEqual(response.status_code, 201)
        proposal = response.get_json()
        role_objects = {item["role"]: item["object"] for item in proposal["objects"]}
        self.assertEqual(set(role_objects), {"building", "platform", "access"})
        building_id = role_objects["building"]["id"]
        self.assertEqual(role_objects["platform"]["parameters"]["building_object_id"], building_id)
        self.assertEqual(role_objects["access"]["parameters"]["building_object_id"], building_id)
        self.assertEqual(proposal["earthwork_result"]["scenario_object_id"], role_objects["platform"]["id"])
        self.assertEqual(proposal["earthwork_result"]["status"], "success")
        stored = self.client.get(f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}").get_json()
        self.assertEqual(len(stored["objects"]), 3)
        results = self.client.get(f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}/results").get_json()["results"]
        self.assertEqual(len(results), 1)

    def test_guided_building_rejects_an_outside_location(self):
        project = self.create_project()
        response = self.client.post(
            f"/api/v2/projects/{project['id']}/planning/building-preview",
            json={"center": [30, 30], "model": "annex"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("fora", response.get_json()["error"].lower())

    def test_guided_building_rejects_fractional_floors(self):
        project = self.create_project()
        response = self.client.post(
            f"/api/v2/projects/{project['id']}/planning/building-preview",
            json={"center": [5, 5], "model": "annex", "floors": 1.5},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("inteiro", response.get_json()["error"].lower())

    def test_site_constraints_are_normalized_with_sources_and_limitations(self):
        lat, lon = 37.357448, -8.308065
        parcel = {
            "geometry": {"type": "Polygon", "coordinates": [[[lon - .002, lat - .002], [lon + .002, lat - .002], [lon + .002, lat + .002], [lon - .002, lat + .002], [lon - .002, lat - .002]]]},
            "crs": "EPSG:4326",
        }
        project = self.client.post("/api/v2/projects", json={"name": "Condicionantes", "base_parcel": parcel}).get_json()
        scenario = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Implantação"}).get_json()
        proposal = self.client.post(
            f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}/planning/building-proposal",
            json={"center": [lon, lat], "model": "annex", "include_platform": False, "include_access": False},
        ).get_json()
        building = proposal["objects"][0]["object"]
        legal = {
            "answer": {"classificacao_solo": "Solo rústico", "condicionantes_ativas": ["REN"], "riscos_identificados": ["Instabilidade"]},
            "confidence": {"label": "Alta"}, "limitations": ["Consulta pontual."],
            "sources": ["SIG municipal"], "generated_at": "2026-01-01T00:00:00Z",
        }
        environmental = {
            "answer": {"classe_risco_incendio": "Elevado", "ja_ardeu_historicamente": True, "distancia_estrada_mais_proxima_m": 400, "faixa_gestao_combustivel": {"distancia_m": 50}},
            "limitations": ["Distância aproximada."], "sources": ["SIG municipal", "Diário da República"],
            "generated_at": "2026-01-01T00:00:00Z",
        }
        with patch("motor_juridico.montar_conclusao", return_value=legal), patch("motor_ambiental.montar_conclusao", return_value=environmental):
            response = self.client.post("/api/v2/simulations/run", json={
                "scenario_id": scenario["id"], "scenario_object_id": building["id"], "engine_type": "site_constraints"
            })
        self.assertEqual(response.status_code, 201)
        result = response.get_json()
        self.assertEqual(result["metrics"]["constraint_count"], 1)
        self.assertEqual(result["metrics"]["risk_count"], 1)
        self.assertEqual(result["metrics"]["sources"], ["SIG municipal", "Diário da República"])
        self.assertTrue(result["limitations"])

    def test_suitability_grid_is_terrain_only_and_explainable(self):
        lat, lon = 37.357448, -8.308065
        parcel = {
            "geometry": {"type": "Polygon", "coordinates": [[[lon - .002, lat - .002], [lon + .002, lat - .002], [lon + .002, lat + .002], [lon - .002, lat + .002], [lon - .002, lat - .002]]]},
            "crs": "EPSG:4326",
        }
        project = self.client.post("/api/v2/projects", json={"name": "Adequação", "base_parcel": parcel}).get_json()
        response = self.client.get(f"/api/v2/projects/{project['id']}/terrain/suitability?objective=building")
        self.assertEqual(response.status_code, 200)
        suitability = response.get_json()
        self.assertEqual(suitability["type"], "FeatureCollection")
        self.assertTrue(suitability["features"])
        self.assertLessEqual(len(suitability["features"]), 45 * 45)
        self.assertTrue({feature["properties"]["category"] for feature in suitability["features"]} <= {"favorable", "attention", "constrained"})
        self.assertIn("declive", suitability["limitations"][0].lower())
        self.assertEqual(suitability["source"]["native_resolution_m"], 2.0)

    def test_comparison_uses_current_results_and_marks_missing_data_gray(self):
        lat, lon = 37.357448, -8.308065
        parcel = {
            "geometry": {"type": "Polygon", "coordinates": [[[lon - .002, lat - .002], [lon + .002, lat - .002], [lon + .002, lat + .002], [lon - .002, lat + .002], [lon - .002, lat - .002]]]},
            "crs": "EPSG:4326",
        }
        project = self.client.post("/api/v2/projects", json={"name": "Comparação", "base_parcel": parcel}).get_json()
        first = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Alternativa A"}).get_json()
        proposal = self.client.post(
            f"/api/v2/projects/{project['id']}/scenarios/{first['id']}/planning/building-proposal",
            json={"center": [lon, lat], "model": "single_storey_house", "include_platform": True, "include_access": True},
        ).get_json()
        building = next(entry["object"] for entry in proposal["objects"] if entry["role"] == "building")
        legal = {
            "answer": {"classificacao_solo": "Solo", "condicionantes_ativas": ["Nenhuma identificada"], "riscos_identificados": ["Nenhum identificado"]},
            "confidence": {"label": "Alta"}, "limitations": [], "sources": ["SIG"], "generated_at": "2026-01-01T00:00:00Z",
        }
        environmental = {
            "answer": {"classe_risco_incendio": "Baixo", "ja_ardeu_historicamente": False, "distancia_estrada_mais_proxima_m": 200, "faixa_gestao_combustivel": {"distancia_m": 10}},
            "limitations": [], "sources": ["SIG"], "generated_at": "2026-01-01T00:00:00Z",
        }
        with patch("motor_juridico.montar_conclusao", return_value=legal), patch("motor_ambiental.montar_conclusao", return_value=environmental):
            self.client.post("/api/v2/simulations/run", json={"scenario_id": first["id"], "scenario_object_id": building["id"], "engine_type": "site_constraints"})
        second = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Alternativa B"}).get_json()
        response = self.client.post(f"/api/v2/projects/{project['id']}/comparison", json={"scenario_ids": [first["id"], second["id"]]})
        self.assertEqual(response.status_code, 200)
        comparison = response.get_json()
        self.assertFalse(comparison["method"]["ranking"])
        compared = {item["scenario_name"]: item for item in comparison["scenarios"]}
        self.assertNotEqual(compared["Alternativa A"]["dimensions"]["earthwork"]["status"], "gray")
        self.assertNotEqual(compared["Alternativa A"]["dimensions"]["constraints"]["status"], "gray")
        self.assertEqual(compared["Alternativa B"]["dimensions"]["objective"]["status"], "gray")
        self.assertEqual(compared["Alternativa B"]["dimensions"]["constraints"]["status"], "gray")
        self.assertIn("não representam aprovação", comparison["disclaimer"])

    def test_phase5d_exports_all_scenario_image_views(self):
        lat, lon = 37.357448, -8.308065
        parcel = {
            "geometry": {"type": "Polygon", "coordinates": [[[lon - .002, lat - .002], [lon + .002, lat - .002], [lon + .002, lat + .002], [lon - .002, lat + .002], [lon - .002, lat - .002]]]},
            "crs": "EPSG:4326",
        }
        project = self.client.post("/api/v2/projects", json={"name": "Exportação", "base_parcel": parcel}).get_json()
        scenario = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Alternativa A"}).get_json()
        self.client.post(
            f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}/planning/building-proposal",
            json={"center": [lon, lat], "model": "annex", "include_platform": True, "include_access": True},
        )
        for view in ("2d", "3d", "proposal"):
            response = self.client.get(f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}/exports/image?view={view}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "image/png")
            self.assertTrue(response.data.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertGreater(len(response.data), 10_000)
            self.assertIn("attachment", response.headers["Content-Disposition"])
        invalid = self.client.get(f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}/exports/image?view=unknown")
        self.assertEqual(invalid.status_code, 400)
        invalid_bounds = self.client.get(f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}/exports/image?view=2d&bbox=1,2,0,3")
        self.assertEqual(invalid_bounds.status_code, 400)

    def test_phase5d_simple_and_requested_technical_reports_are_pdf(self):
        lat, lon = 37.357448, -8.308065
        parcel = {
            "geometry": {"type": "Polygon", "coordinates": [[[lon - .002, lat - .002], [lon + .002, lat - .002], [lon + .002, lat + .002], [lon - .002, lat + .002], [lon - .002, lat - .002]]]},
            "crs": "EPSG:4326",
        }
        project = self.client.post("/api/v2/projects", json={"name": "Relatório", "base_parcel": parcel}).get_json()
        scenario = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Implantação"}).get_json()
        self.client.post(
            f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}/planning/building-proposal",
            json={"center": [lon, lat], "model": "single_storey_house", "include_platform": True, "include_access": True},
        )
        sizes = {}
        for level in ("simple", "technical"):
            response = self.client.get(f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}/exports/report?level={level}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "application/pdf")
            self.assertTrue(response.data.startswith(b"%PDF"))
            self.assertGreater(len(response.data), 25_000)
            self.assertIn("attachment", response.headers["Content-Disposition"])
            sizes[level] = len(response.data)
        self.assertGreater(sizes["technical"], sizes["simple"])
        invalid = self.client.get(f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}/exports/report?level=full")
        self.assertEqual(invalid.status_code, 400)

    def test_zone_engines_run_without_loading_the_mdt(self):
        project = self.create_project()
        geometry = {"type": "Polygon", "coordinates": [[[1, 1], [4, 1], [1, 4], [1, 1]]]}
        self.client.post(
            f"/api/v2/projects/{project['id']}/objects",
            json={"type": "zone", "name": "Zona", "geometry": geometry, "parameters": {"peakpower_kw": 2}},
        )
        scenario = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Contexto"}).get_json()
        scenario_object = scenario["objects"][0]
        solar = {"answer": {"melhor_caso": {"potencial": "Elevado", "producao_especifica_kwh_por_kwp_ano": 1600, "irradiacao_anual_kwh_m2": 1900, "angulo_otimo_graus": 30}, "terreno_real": {"declive_estimado_graus": 4, "producao_estimada_kwh_por_kwp_ano": 1500}}, "limitations": []}
        water = {"answer": {"indicadores_num_raio_1km": {"agua_superficie_perto": True, "captacao_subterranea_perto": False, "infraestrutura_rega_perto": True}, "precipitacao_media_mm_ano": 500, "sistema_aquifero": {"nome": "Aquífero"}, "pontos_agua_subterranea": {"total_no_raio": 3}}, "confidence": {"label": "Média"}, "limitations": []}
        with patch("motor_solar.montar_conclusao", return_value=solar), patch("motor_hidrico.montar_conclusao", return_value=water):
            solar_response = self.client.post("/api/v2/simulations/run", json={"scenario_id": scenario["id"], "scenario_object_id": scenario_object["id"], "engine_type": "solar_potential"})
            water_response = self.client.post("/api/v2/simulations/run", json={"scenario_id": scenario["id"], "scenario_object_id": scenario_object["id"], "engine_type": "water_context"})
        self.assertEqual(solar_response.status_code, 201)
        self.assertEqual(water_response.status_code, 201)
        results = self.client.get(f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}/results").get_json()["results"]
        self.assertEqual({result["engine_type"] for result in results}, {"solar_potential", "water_context"})

    def test_project_terrain_mesh_is_bounded_and_project_scoped(self):
        lat, lon = 37.357448, -8.308065
        parcel = {
            "geometry": {"type": "Polygon", "coordinates": [[[lon - .002, lat - .002], [lon + .002, lat - .002], [lon + .002, lat + .002], [lon - .002, lat + .002], [lon - .002, lat - .002]]]},
            "crs": "EPSG:4326",
        }
        project = self.client.post("/api/v2/projects", json={"name": "Terreno 3D", "base_parcel": parcel}).get_json()
        geometry = {"type": "Polygon", "coordinates": [[[lon - .0005, lat - .0005], [lon + .0005, lat - .0005], [lon, lat + .0005], [lon - .0005, lat - .0005]]]}
        project_object = self.client.post(
            f"/api/v2/projects/{project['id']}/objects",
            json={"type": "platform", "name": "Plataforma", "geometry": geometry, "parameters": {}},
        ).get_json()["object"]

        response = self.client.get(f"/api/v2/projects/{project['id']}/terrain/mesh")
        self.assertEqual(response.status_code, 200)
        mesh = response.get_json()
        self.assertLessEqual(max(mesh["n_linhas"], mesh["n_cols"]), 180)
        self.assertGreater(mesh["elevacao_max"], mesh["elevacao_min"])
        self.assertGreater(mesh["bbox_3763"]["xmin"], 100000)
        self.assertGreater(mesh["bbox_3763"]["ymin"], 0)
        self.assertLess(mesh["orthophoto_bbox"]["xmin"], 0)
        self.assertLess(mesh["orthophoto_bbox"]["ymin"], 0)
        self.assertEqual(mesh["source"]["native_resolution_m"], 2.0)
        self.assertTrue(mesh["source"]["limitations"])
        self.assertEqual({overlay["id"] for overlay in mesh["overlays"]}, {project["base_parcel"]["id"], project_object["id"]})
        projected = next(overlay for overlay in mesh["overlays"] if overlay["id"] == project_object["id"])
        self.assertTrue(all(point["elevation"] is not None for point in projected["geometry"]["paths"][0]))

    def test_scenario_terrain_mesh_uses_scenario_object_identity(self):
        lat, lon = 37.357448, -8.308065
        parcel = {
            "geometry": {"type": "Polygon", "coordinates": [[[lon - .002, lat - .002], [lon + .002, lat - .002], [lon + .002, lat + .002], [lon - .002, lat + .002], [lon - .002, lat - .002]]]},
            "crs": "EPSG:4326",
        }
        project = self.client.post("/api/v2/projects", json={"name": "Cenário 3D", "base_parcel": parcel}).get_json()
        geometry = {"type": "Polygon", "coordinates": [[[lon - .0005, lat - .0005], [lon + .0005, lat - .0005], [lon, lat + .0005], [lon - .0005, lat - .0005]]]}
        project_object = self.client.post(
            f"/api/v2/projects/{project['id']}/objects",
            json={"type": "platform", "name": "Plataforma", "geometry": geometry, "parameters": {}},
        ).get_json()["object"]
        scenario = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Alternativa 3D"}).get_json()
        scenario_object = scenario["objects"][0]

        response = self.client.get(f"/api/v2/projects/{project['id']}/terrain/mesh?scenario_id={scenario['id']}")
        self.assertEqual(response.status_code, 200)
        mesh = response.get_json()
        overlay_ids = {overlay["id"] for overlay in mesh["overlays"]}
        self.assertIn(scenario_object["id"], overlay_ids)
        self.assertNotIn(project_object["id"], overlay_ids)
        self.assertEqual(mesh["scenario_id"], scenario["id"])

    def test_scenario_snapshot_survives_project_object_deletion(self):
        project = self.create_project()
        geometry = {"type": "Polygon", "coordinates": [[[1, 1], [4, 1], [1, 4], [1, 1]]]}
        object_id = self.client.post(f"/api/v2/projects/{project['id']}/objects", json={"type": "zone", "name": "Zona", "geometry": geometry, "parameters": {}}).get_json()["object"]["id"]
        scenario = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Snapshot"}).get_json()
        self.assertEqual(scenario["objects"][0]["original_object_id"], object_id)
        self.client.delete(f"/api/v2/projects/{project['id']}/objects/{object_id}")
        preserved = self.client.get(f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}").get_json()
        self.assertIsNone(preserved["objects"][0]["original_object_id"])

    def test_scenario_duplication_creates_new_object_identity(self):
        project = self.create_project()
        geometry = {"type": "Polygon", "coordinates": [[[1, 1], [4, 1], [1, 4], [1, 1]]]}
        object_id = self.client.post(f"/api/v2/projects/{project['id']}/objects", json={"type": "zone", "name": "Zona", "geometry": geometry, "parameters": {}}).get_json()["object"]["id"]
        original = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Original"}).get_json()
        duplicate = self.client.post(f"/api/v2/projects/{project['id']}/scenarios/{original['id']}/duplicate", json={"name": "Cópia"}).get_json()
        self.assertNotEqual(duplicate["id"], original["id"])
        self.assertNotEqual(duplicate["objects"][0]["id"], original["objects"][0]["id"])
        self.assertEqual(duplicate["objects"][0]["original_object_id"], object_id)
        self.assertEqual(self.client.get(f"/api/v2/projects/{project['id']}/scenarios/{duplicate['id']}/results").get_json()["results"], [])

    def test_explicit_refresh_preserves_identity_and_makes_result_stale(self):
        lat, lon = 37.357448, -8.308065
        parcel = {"geometry": {"type": "Polygon", "coordinates": [[[lon - .002, lat - .002], [lon + .002, lat - .002], [lon + .002, lat + .002], [lon - .002, lat + .002], [lon - .002, lat - .002]]]}, "crs": "EPSG:4326"}
        project = self.client.post("/api/v2/projects", json={"name": "Stale", "base_parcel": parcel}).get_json()
        geometry = {"type": "Polygon", "coordinates": [[[lon - .0005, lat - .0005], [lon + .0005, lat - .0005], [lon, lat + .0005], [lon - .0005, lat - .0005]]]}
        project_object = self.client.post(f"/api/v2/projects/{project['id']}/objects", json={"type": "platform", "name": "Plataforma", "geometry": geometry, "parameters": {}}).get_json()["object"]
        scenario = self.client.post(f"/api/v2/projects/{project['id']}/scenarios", json={"name": "Cenário"}).get_json()
        snapshot = scenario["objects"][0]
        self.client.post("/api/v2/simulations/run", json={"scenario_id": scenario["id"], "scenario_object_id": snapshot["id"], "engine_type": "earthwork"})
        updated_geometry = {"type": "Polygon", "coordinates": [[[lon - .0006, lat - .0005], [lon + .0005, lat - .0005], [lon, lat + .0006], [lon - .0006, lat - .0005]]]}
        self.client.put(f"/api/v2/projects/{project['id']}/objects/{project_object['id']}", json={"type": "platform", "name": "Plataforma revista", "geometry": updated_geometry, "parameters": {}})
        refreshed = self.client.post(f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}/objects/{snapshot['id']}/update-from-project")
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(refreshed.get_json()["id"], snapshot["id"])
        self.assertEqual(refreshed.get_json()["snapshot_version"], 2)
        results = self.client.get(f"/api/v2/projects/{project['id']}/scenarios/{scenario['id']}/results").get_json()["results"]
        self.assertTrue(results[0]["is_stale"])


if __name__ == "__main__":
    unittest.main()
