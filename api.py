"""Flask routes for the Phase 1 V2 workspace API."""

from time import perf_counter

from flask import Blueprint, current_app, jsonify, request

from .repository import ProjectRepository
from .adapters import ADAPTERS
from .terrain import TerrainContext
from .type_registry import TYPE_REGISTRY
from .validation import ValidationError, validate_geometry, validate_project_object


api = Blueprint("atlas_v2", __name__, url_prefix="/api/v2")


def repository():
    return current_app.extensions["atlas_v2_repository"]


def error(message, status=400):
    return jsonify({"error": message}), status


def project_or_404(project_id):
    project = repository().get_project(project_id)
    return project


def bounding_box(geometry):
    ring = geometry["coordinates"][0]
    xs = [point[0] for point in ring]
    ys = [point[1] for point in ring]
    return {"min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}


@api.get("/types")
def get_types():
    return jsonify(TYPE_REGISTRY)


@api.get("/projects")
def list_projects():
    return jsonify({"projects": repository().list_projects()})


@api.post("/projects")
def create_project():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    base_parcel = data.get("base_parcel")
    if not isinstance(name, str) or not name.strip():
        return error("O nome do projeto é obrigatório.")
    if not isinstance(base_parcel, dict):
        return error("A BaseParcel é obrigatória.")
    try:
        geometry = base_parcel["geometry"]
        validate_geometry(geometry, ["Polygon"])
    except (KeyError, ValidationError) as exc:
        return error(str(exc))
    crs = base_parcel.get("crs")
    if not isinstance(crs, str) or not crs.strip():
        return error("O CRS da BaseParcel é obrigatório.")
    project = repository().create_project(name.strip(), {
        "geometry": geometry,
        "bounding_box": bounding_box(geometry),
        "crs": crs.strip(),
        "terrain_source_ref": base_parcel.get("terrain_source_ref"),
    })
    return jsonify(project), 201


@api.get("/projects/<project_id>")
def get_project(project_id):
    project = project_or_404(project_id)
    return jsonify(project) if project else error("Projeto não encontrado.", 404)


@api.put("/projects/<project_id>")
def update_project(project_id):
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return error("O nome do projeto é obrigatório.")
    project = repository().update_project(project_id, name.strip())
    return jsonify(project) if project else error("Projeto não encontrado.", 404)


@api.delete("/projects/<project_id>")
def delete_project(project_id):
    return ("", 204) if repository().delete_project(project_id) else error("Projeto não encontrado.", 404)


@api.get("/projects/<project_id>/objects")
def list_objects(project_id):
    if not project_or_404(project_id):
        return error("Projeto não encontrado.", 404)
    return jsonify({"objects": repository().list_objects(project_id)})


def object_payload(project, data):
    object_type, name = data.get("type"), data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("O nome do objeto é obrigatório.")
    warnings = validate_project_object(object_type, data.get("geometry"), data.get("parameters", {}), project["base_parcel"]["geometry"])
    return {"type": object_type, "name": name.strip(), "geometry": data["geometry"], "parameters": data.get("parameters", {})}, warnings


@api.post("/projects/<project_id>/objects")
def create_object(project_id):
    project = project_or_404(project_id)
    if not project:
        return error("Projeto não encontrado.", 404)
    try:
        payload, warnings = object_payload(project, request.get_json(silent=True) or {})
    except ValidationError as exc:
        return error(str(exc))
    return jsonify({"object": repository().create_object(project_id, payload), "warnings": warnings}), 201


@api.put("/projects/<project_id>/objects/<object_id>")
def update_object(project_id, object_id):
    project = project_or_404(project_id)
    if not project:
        return error("Projeto não encontrado.", 404)
    try:
        payload, warnings = object_payload(project, request.get_json(silent=True) or {})
    except ValidationError as exc:
        return error(str(exc))
    stored = repository().update_object(project_id, object_id, payload)
    return jsonify({"object": stored, "warnings": warnings}) if stored else error("Objeto não encontrado.", 404)


@api.delete("/projects/<project_id>/objects/<object_id>")
def delete_object(project_id, object_id):
    return ("", 204) if repository().delete_object(project_id, object_id) else error("Objeto não encontrado.", 404)


@api.get("/projects/<project_id>/scenarios")
def list_scenarios(project_id):
    if not project_or_404(project_id):
        return error("Projeto não encontrado.", 404)
    return jsonify({"scenarios": repository().list_scenarios(project_id)})


@api.post("/projects/<project_id>/scenarios")
def create_scenario(project_id):
    if not project_or_404(project_id):
        return error("Projeto não encontrado.", 404)
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return error("O nome do cenário é obrigatório.")
    return jsonify(repository().create_scenario(project_id, name.strip())), 201


@api.get("/projects/<project_id>/scenarios/<scenario_id>")
def get_scenario(project_id, scenario_id):
    scenario = repository().get_scenario(project_id, scenario_id)
    return jsonify(scenario) if scenario else error("Cenário não encontrado.", 404)


@api.put("/projects/<project_id>/scenarios/<scenario_id>")
def update_scenario(project_id, scenario_id):
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return error("O nome do cenário é obrigatório.")
    scenario = repository().update_scenario(project_id, scenario_id, name.strip())
    return jsonify(scenario) if scenario else error("Cenário não encontrado.", 404)


@api.delete("/projects/<project_id>/scenarios/<scenario_id>")
def delete_scenario(project_id, scenario_id):
    return ("", 204) if repository().delete_scenario(project_id, scenario_id) else error("Cenário não encontrado.", 404)


@api.post("/projects/<project_id>/scenarios/<scenario_id>/duplicate")
def duplicate_scenario(project_id, scenario_id):
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return error("O nome do cenário duplicado é obrigatório.")
    duplicate = repository().duplicate_scenario(project_id, scenario_id, name.strip())
    return jsonify(duplicate) if duplicate else error("Cenário não encontrado.", 404)


@api.put("/projects/<project_id>/scenarios/<scenario_id>/objects/<scenario_object_id>")
def update_scenario_object(project_id, scenario_id, scenario_object_id):
    project = project_or_404(project_id)
    if not project:
        return error("Projeto não encontrado.", 404)
    if not repository().get_scenario(project_id, scenario_id):
        return error("Cenário não encontrado.", 404)
    try:
        payload, warnings = object_payload(project, request.get_json(silent=True) or {})
    except ValidationError as exc:
        return error(str(exc))
    scenario_object = repository().update_scenario_object(scenario_id, scenario_object_id, payload)
    return jsonify({"object": scenario_object, "warnings": warnings}) if scenario_object else error("Objeto de cenário não encontrado.", 404)


@api.post("/projects/<project_id>/scenarios/<scenario_id>/objects")
def create_scenario_object(project_id, scenario_id):
    project = project_or_404(project_id)
    if not project:
        return error("Projeto não encontrado.", 404)
    if not repository().get_scenario(project_id, scenario_id):
        return error("Cenário não encontrado.", 404)
    try:
        payload, warnings = object_payload(project, request.get_json(silent=True) or {})
    except ValidationError as exc:
        return error(str(exc))
    return jsonify({"object": repository().create_scenario_object(scenario_id, payload), "warnings": warnings}), 201


@api.delete("/projects/<project_id>/scenarios/<scenario_id>/objects/<scenario_object_id>")
def delete_scenario_object(project_id, scenario_id, scenario_object_id):
    if not repository().get_scenario(project_id, scenario_id):
        return error("Cenário não encontrado.", 404)
    return ("", 204) if repository().delete_scenario_object(scenario_id, scenario_object_id) else error("Objeto de cenário não encontrado.", 404)


@api.post("/projects/<project_id>/scenarios/<scenario_id>/objects/<scenario_object_id>/update-from-project")
def update_scenario_object_from_project(project_id, scenario_id, scenario_object_id):
    if not repository().get_scenario(project_id, scenario_id):
        return error("Cenário não encontrado.", 404)
    scenario_object = repository().update_scenario_object_from_project(project_id, scenario_id, scenario_object_id)
    if not scenario_object:
        return error("O objeto de cenário não tem uma origem de projeto disponível.", 409)
    return jsonify(scenario_object)


@api.get("/projects/<project_id>/scenarios/<scenario_id>/results")
def list_scenario_results(project_id, scenario_id):
    if not repository().get_scenario(project_id, scenario_id):
        return error("Cenário não encontrado.", 404)
    return jsonify({"results": repository().list_simulation_results(scenario_id)})


def terrain_context(project):
    contexts = current_app.extensions.setdefault("atlas_v2_terrain_contexts", {})
    if project["id"] not in contexts:
        contexts[project["id"]] = TerrainContext(project["id"], current_app.config["ATLAS_TERRAIN_NORTH"], current_app.config["ATLAS_TERRAIN_SOUTH"])
    return contexts[project["id"]]


@api.get("/projects/<project_id>/terrain/mesh")
def get_project_terrain_mesh(project_id):
    """Return a bounded 3D mesh and projected workspace overlays."""
    project = project_or_404(project_id)
    if not project:
        return error("Projeto não encontrado.", 404)

    scenario_id = request.args.get("scenario_id")
    if scenario_id:
        scenario = repository().get_scenario(project_id, scenario_id)
        if not scenario:
            return error("Cenário não encontrado.", 404)
        objects = scenario["objects"]
    else:
        scenario = None
        objects = repository().list_objects(project_id)

    geometries = [project["base_parcel"]["geometry"]] + [item["geometry"] for item in objects]
    try:
        context = terrain_context(project)
        mesh = context.mesh_for_geometries(geometries)
        clip = mesh.pop("_clip")
        overlays = [{
            "id": project["base_parcel"]["id"],
            "type": "base_parcel",
            "name": project["name"],
            "geometry": context.project_geojson(project["base_parcel"]["geometry"], clip),
        }]
        overlays.extend({
            "id": item["id"],
            "type": item["type"],
            "name": item["name"],
            "geometry": context.project_geojson(item["geometry"], clip),
        } for item in objects)
        mesh.update({
            "project_id": project_id,
            "project_name": project["name"],
            "scenario_id": scenario_id,
            "scenario_name": scenario["name"] if scenario else None,
            "overlays": overlays,
        })
        return jsonify(mesh)
    except (ValueError, FileNotFoundError) as exc:
        return error(str(exc))


@api.post("/simulations/run")
def run_simulation():
    data = request.get_json(silent=True) or {}
    scenario_id, scenario_object_id, engine_type = data.get("scenario_id"), data.get("scenario_object_id"), data.get("engine_type")
    if not all(isinstance(value, str) and value for value in (scenario_id, scenario_object_id, engine_type)):
        return error("scenario_id, scenario_object_id e engine_type são obrigatórios.")
    adapter = ADAPTERS.get(engine_type)
    if not adapter:
        return error("Motor não suportado.")
    scenario = None
    for project in repository().list_projects():
        scenario = repository().get_scenario(project["id"], scenario_id)
        if scenario:
            break
    if not scenario:
        return error("Cenário não encontrado.", 404)
    scenario_object = repository().get_scenario_object(scenario_id, scenario_object_id)
    if not scenario_object:
        return error("Objeto de cenário não encontrado.", 404)
    parameters = data["simulation_parameters"] if "simulation_parameters" in data else scenario_object["parameters"]
    try:
        adapter.validate_input(scenario_object, parameters)
        started = perf_counter()
        context = terrain_context(project) if getattr(adapter, "requires_terrain", True) else None
        raw_output = adapter.execute(context, scenario_object, parameters)
        normalized = adapter.from_motor_output(raw_output, scenario_object, parameters)
        normalized["computation_time_ms"] = round((perf_counter() - started) * 1000)
        stored = repository().replace_simulation_result(scenario_id, scenario_object_id, engine_type, normalized)
        stored["is_stale"] = False
        return jsonify(stored), 201
    except (ValidationError, ValueError, FileNotFoundError) as exc:
        return error(str(exc))


def init_app(app):
    repo = ProjectRepository(app.config["ATLAS_V2_DATABASE"])
    repo.initialize()
    app.extensions["atlas_v2_repository"] = repo
    app.extensions["atlas_v2_terrain_contexts"] = {}
    app.register_blueprint(api)
