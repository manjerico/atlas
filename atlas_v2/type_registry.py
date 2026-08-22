"""Configuration-only object semantics for Atlas V2."""

TYPE_REGISTRY = {
    "building": {
        "allowed_geometry_types": ["Polygon"],
        "parameter_schema": {
            "model": {"type": "string", "required": True, "enum": ["single_storey_house", "two_storey_house", "warehouse", "annex"]},
            "width_m": {"type": "number", "required": True, "minimum": 3, "maximum": 80},
            "length_m": {"type": "number", "required": True, "minimum": 3, "maximum": 120},
            "floors": {"type": "integer", "required": True, "minimum": 1, "maximum": 4},
            "height_m": {"type": "number", "required": True, "minimum": 2, "maximum": 18},
            "orientation_degrees": {"type": "number", "required": True, "minimum": 0, "maximum": 359.99},
            "earthwork_tolerance": {"type": "string", "required": True, "enum": ["low", "balanced", "high"]},
            "proposal_ref": {"type": "string", "required": True},
        },
        "presets": {
            "single_storey_house": {"label": "Casa térrea", "width_m": 10, "length_m": 14, "floors": 1, "height_m": 3.4},
            "two_storey_house": {"label": "Casa de dois pisos", "width_m": 9, "length_m": 11, "floors": 2, "height_m": 6.6},
            "warehouse": {"label": "Armazém", "width_m": 14, "length_m": 24, "floors": 1, "height_m": 6},
            "annex": {"label": "Anexo", "width_m": 6, "length_m": 8, "floors": 1, "height_m": 3},
        },
        "render_style": "building",
        "engines": ["site_constraints"],
        "category": "construction",
        "modifiable_terrain": False,
        "allow_outside_parcel": False,
    },
    "zone": {
        "allowed_geometry_types": ["Polygon"],
        "parameter_schema": {"peakpower_kw": {"type": "number", "required": False}},
        "render_style": "zone_outline",
        "engines": ["solar_potential", "water_context"],
        "category": "zone",
        "modifiable_terrain": False,
        "allow_outside_parcel": False,
    },
    "pond": {
        "allowed_geometry_types": ["Polygon"],
        "parameter_schema": {"target_depth": {"type": "number", "required": False}},
        "render_style": "water_body",
        "engines": [],
        "category": "water",
        "modifiable_terrain": True,
        "allow_outside_parcel": False,
    },
    "platform": {
        "allowed_geometry_types": ["Polygon"],
        "parameter_schema": {
            "building_object_id": {"type": "string", "required": False},
            "margin_m": {"type": "number", "required": False, "minimum": 0, "maximum": 20},
            "proposal_ref": {"type": "string", "required": False},
            "generation_method": {"type": "string", "required": False, "enum": ["building_buffer"]},
        },
        "render_style": "platform",
        "engines": ["earthwork"],
        "category": "terrain",
        "modifiable_terrain": True,
        "allow_outside_parcel": False,
    },
    "access": {
        "allowed_geometry_types": ["LineString", "Polygon"],
        "parameter_schema": {
            "building_object_id": {"type": "string", "required": False},
            "proposal_ref": {"type": "string", "required": False},
            "generation_method": {"type": "string", "required": False, "enum": ["nearest_boundary"]},
            "estimated_length_m": {"type": "number", "required": False, "minimum": 0},
            "width_m": {"type": "number", "required": False, "minimum": 1, "maximum": 12},
        },
        "render_style": "path",
        "engines": [],
        "category": "access",
        "modifiable_terrain": False,
        "allow_outside_parcel": False,
    },
    "crop_area": {
        "allowed_geometry_types": ["Polygon"],
        "parameter_schema": {},
        "render_style": "crop_zone",
        "engines": ["cultivable_area"],
        "category": "agriculture",
        "modifiable_terrain": False,
        "allow_outside_parcel": False,
    },
}


def get_type_definition(object_type):
    return TYPE_REGISTRY.get(object_type)
