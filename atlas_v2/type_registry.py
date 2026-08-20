"""Configuration-only object semantics for Atlas V2."""

TYPE_REGISTRY = {
    "zone": {
        "allowed_geometry_types": ["Polygon"],
        "parameter_schema": {},
        "render_style": "zone_outline",
        "engines": [],
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
        "parameter_schema": {},
        "render_style": "platform",
        "engines": ["earthwork"],
        "category": "terrain",
        "modifiable_terrain": True,
        "allow_outside_parcel": False,
    },
    "access": {
        "allowed_geometry_types": ["LineString", "Polygon"],
        "parameter_schema": {},
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
        "engines": [],
        "category": "agriculture",
        "modifiable_terrain": False,
        "allow_outside_parcel": False,
    },
}


def get_type_definition(object_type):
    return TYPE_REGISTRY.get(object_type)
