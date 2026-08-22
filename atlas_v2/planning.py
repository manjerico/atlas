"""Preliminary, deterministic geometry generation for the Phase 5B assistant."""

import math

from motor_charca import en_para_latlon, latlon_para_en

from .type_registry import get_type_definition
from .validation import ValidationError


PLANNING_LIMITATIONS = [
    "A implantação é uma proposta preliminar e não confirma viabilidade construtiva ou licenciamento.",
    "A plataforma e o acesso são geometrias iniciais editáveis; exigem validação topográfica, geotécnica e técnica.",
    "As dimensões não incluem automaticamente paredes, fundações, muros, drenagem ou afastamentos regulamentares.",
]


def _number(value, label, default=None):
    if value is None:
        value = default
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValidationError(f"{label} tem de ser um número válido.")
    return float(value)


def _flag(data, name, default):
    value = data.get(name, default)
    if not isinstance(value, bool):
        raise ValidationError(f"O campo '{name}' tem de ser verdadeiro ou falso.")
    return value


def _rectangle(center, width_m, length_m, orientation_degrees):
    lon, lat = center
    east, north = latlon_para_en(lat, lon)
    angle = math.radians(orientation_degrees)
    along = (math.sin(angle), math.cos(angle))
    across = (math.cos(angle), -math.sin(angle))
    half_length, half_width = length_m / 2, width_m / 2
    corners = []
    for length_sign, width_sign in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        corner_east = east + length_sign * half_length * along[0] + width_sign * half_width * across[0]
        corner_north = north + length_sign * half_length * along[1] + width_sign * half_width * across[1]
        corner_lat, corner_lon = en_para_latlon(corner_east, corner_north)
        corners.append([corner_lon, corner_lat])
    corners.append(corners[0])
    return {"type": "Polygon", "coordinates": [corners]}


def _nearest_boundary_point(center, parcel_geometry):
    center_east, center_north = latlon_para_en(center[1], center[0])
    best = None
    ring = parcel_geometry["coordinates"][0]
    for first, second in zip(ring, ring[1:]):
        first_east, first_north = latlon_para_en(first[1], first[0])
        second_east, second_north = latlon_para_en(second[1], second[0])
        delta_east, delta_north = second_east - first_east, second_north - first_north
        length_squared = delta_east ** 2 + delta_north ** 2
        if length_squared == 0:
            ratio = 0
        else:
            ratio = max(0, min(1, ((center_east - first_east) * delta_east + (center_north - first_north) * delta_north) / length_squared))
        point_east = first_east + ratio * delta_east
        point_north = first_north + ratio * delta_north
        distance = math.hypot(center_east - point_east, center_north - point_north)
        if best is None or distance < best[0]:
            best = (distance, point_east, point_north)
    if best is None:
        raise ValidationError("Não foi possível determinar um ponto de ligação ao limite da parcela.")
    point_lat, point_lon = en_para_latlon(best[1], best[2])
    return [point_lon, point_lat], best[0]


def building_proposal(base_parcel_geometry, data, proposal_ref):
    """Return editable generic objects for one guided building proposal."""
    center = data.get("center")
    if not isinstance(center, list) or len(center) != 2:
        raise ValidationError("Seleciona no mapa o centro aproximado do edifício.")
    lon = _number(center[0], "A longitude")
    lat = _number(center[1], "A latitude")
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValidationError("A localização indicada não é válida.")
    center = [lon, lat]

    definition = get_type_definition("building")
    model = data.get("model", "single_storey_house")
    preset = definition["presets"].get(model)
    if not preset:
        raise ValidationError("Escolhe um modelo de edifício disponível.")
    width_m = _number(data.get("width_m"), "A largura", preset["width_m"])
    length_m = _number(data.get("length_m"), "O comprimento", preset["length_m"])
    floors_value = _number(data.get("floors"), "O número de pisos", preset["floors"])
    if not floors_value.is_integer():
        raise ValidationError("O número de pisos tem de ser inteiro.")
    floors = int(floors_value)
    height_m = _number(data.get("height_m"), "A altura", preset["height_m"])
    orientation = _number(data.get("orientation_degrees"), "A orientação", 0)
    if not 0 <= orientation < 360:
        raise ValidationError("A orientação tem de estar entre 0 e 359,99 graus.")
    tolerance = data.get("earthwork_tolerance", "balanced")
    if tolerance not in ("low", "balanced", "high"):
        raise ValidationError("Escolhe uma tolerância válida à movimentação de terras.")
    platform_margin = _number(data.get("platform_margin_m"), "A margem da plataforma", 3)
    access_width = _number(data.get("access_width_m"), "A largura do acesso", 3)
    include_platform = _flag(data, "include_platform", True)
    include_access = _flag(data, "include_access", True)

    building_geometry = _rectangle(center, width_m, length_m, orientation)
    building = {
        "type": "building",
        "name": data.get("name") or preset["label"],
        "geometry": building_geometry,
        "parameters": {
            "model": model,
            "width_m": width_m,
            "length_m": length_m,
            "floors": floors,
            "height_m": height_m,
            "orientation_degrees": orientation,
            "earthwork_tolerance": tolerance,
            "proposal_ref": proposal_ref,
        },
    }
    objects = [{"role": "building", "object": building}]

    if include_platform:
        platform_width = width_m + platform_margin * 2
        platform_length = length_m + platform_margin * 2
        objects.append({
            "role": "platform",
            "object": {
                "type": "platform",
                "name": f"Plataforma — {building['name']}",
                "geometry": _rectangle(center, platform_width, platform_length, orientation),
                "parameters": {
                    "margin_m": platform_margin,
                    "proposal_ref": proposal_ref,
                    "generation_method": "building_buffer",
                },
            },
        })

    access_length = None
    if include_access:
        boundary, access_length = _nearest_boundary_point(center, base_parcel_geometry)
        objects.append({
            "role": "access",
            "object": {
                "type": "access",
                "name": f"Acesso inicial — {building['name']}",
                "geometry": {"type": "LineString", "coordinates": [boundary, center]},
                "parameters": {
                    "proposal_ref": proposal_ref,
                    "generation_method": "nearest_boundary",
                    "estimated_length_m": round(access_length, 1),
                    "width_m": access_width,
                },
            },
        })

    return {
        "proposal_ref": proposal_ref,
        "model_label": preset["label"],
        "objects": objects,
        "summary": {
            "footprint_area_m2": round(width_m * length_m, 1),
            "platform_area_m2": round((width_m + platform_margin * 2) * (length_m + platform_margin * 2), 1) if include_platform else None,
            "access_length_m": round(access_length, 1) if access_length is not None else None,
            "orientation_degrees": round(orientation, 1),
        },
        "warnings": [
            "O acesso segue apenas o trajeto direto ao limite mais próximo; declive, curvas e drenagem ainda não foram otimizados."
        ] if include_access else [],
        "limitations": list(PLANNING_LIMITATIONS),
    }
