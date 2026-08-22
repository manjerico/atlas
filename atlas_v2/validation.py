"""Dependency-free GeoJSON and parameter validation for Phase 1."""

from numbers import Real

from .type_registry import get_type_definition


class ValidationError(ValueError):
    pass


def _is_position(value):
    return (
        isinstance(value, (list, tuple))
        and len(value) >= 2
        and all(isinstance(item, Real) and not isinstance(item, bool) for item in value[:2])
    )


def _same_point(a, b):
    return a[0] == b[0] and a[1] == b[1]


def _orientation(a, b, c):
    value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _on_segment(a, b, point):
    return (
        min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= point[1] <= max(a[1], b[1])
        and _orientation(a, b, point) == 0
    )


def _segments_intersect(a, b, c, d):
    ab_c, ab_d = _orientation(a, b, c), _orientation(a, b, d)
    cd_a, cd_b = _orientation(c, d, a), _orientation(c, d, b)
    if ab_c == 0 and _on_segment(a, b, c):
        return True
    if ab_d == 0 and _on_segment(a, b, d):
        return True
    if cd_a == 0 and _on_segment(c, d, a):
        return True
    if cd_b == 0 and _on_segment(c, d, b):
        return True
    return ab_c != ab_d and cd_a != cd_b


def _signed_area(ring):
    return sum(
        ring[index][0] * ring[index + 1][1] - ring[index + 1][0] * ring[index][1]
        for index in range(len(ring) - 1)
    ) / 2


def _polygon_ring(geometry):
    if not isinstance(geometry, dict) or geometry.get("type") != "Polygon":
        raise ValidationError("A geometria tem de ser um Polygon GeoJSON.")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) != 1:
        raise ValidationError("Phase 1 suporta Polygon GeoJSON sem anéis interiores.")
    ring = coordinates[0]
    if not isinstance(ring, list) or len(ring) < 4 or not all(_is_position(point) for point in ring):
        raise ValidationError("Um polígono precisa de pelo menos três vértices válidos.")
    if not _same_point(ring[0], ring[-1]):
        raise ValidationError("O anel do polígono tem de estar fechado.")
    if abs(_signed_area(ring)) == 0:
        raise ValidationError("O polígono não pode ter área zero.")
    edges = list(zip(ring, ring[1:]))
    for index, (start, end) in enumerate(edges):
        if _same_point(start, end):
            raise ValidationError("O polígono contém um segmento de comprimento zero.")
        for other_index, (other_start, other_end) in enumerate(edges[index + 1 :], index + 1):
            adjacent = other_index in {index - 1, index, index + 1} or {index, other_index} == {0, len(edges) - 1}
            if not adjacent and _segments_intersect(start, end, other_start, other_end):
                raise ValidationError("O polígono não pode ter auto-interseções.")
    return ring


def validate_geometry(geometry, allowed_types=None):
    if not isinstance(geometry, dict):
        raise ValidationError("A geometria tem de ser um objeto GeoJSON.")
    geometry_type = geometry.get("type")
    if allowed_types and geometry_type not in allowed_types:
        raise ValidationError("Tipo de geometria incompatível com o tipo de objeto.")
    if geometry_type == "Polygon":
        _polygon_ring(geometry)
    elif geometry_type == "LineString":
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2 or not all(_is_position(point) for point in coordinates):
            raise ValidationError("Uma LineString precisa de pelo menos dois pontos válidos.")
        if all(_same_point(coordinates[0], point) for point in coordinates[1:]):
            raise ValidationError("A LineString não pode ter comprimento zero.")
    else:
        raise ValidationError("A geometria tem de ser Polygon ou LineString.")


def _point_in_polygon(point, ring):
    for start, end in zip(ring, ring[1:]):
        if _on_segment(start, end, point):
            return True
    inside = False
    x, y = point[0], point[1]
    for start, end in zip(ring, ring[1:]):
        if (start[1] > y) != (end[1] > y):
            crossing_x = (end[0] - start[0]) * (y - start[1]) / (end[1] - start[1]) + start[0]
            if x < crossing_x:
                inside = not inside
    return inside


def _geometry_segments(geometry):
    points = geometry["coordinates"][0] if geometry["type"] == "Polygon" else geometry["coordinates"]
    return list(zip(points, points[1:]))


def containment_status(geometry, base_parcel_geometry):
    """Return inside, partial or outside for a valid geometry and base parcel."""
    parcel_ring = _polygon_ring(base_parcel_geometry)
    points = geometry["coordinates"][0][:-1] if geometry["type"] == "Polygon" else geometry["coordinates"]
    points_inside = [_point_in_polygon(point, parcel_ring) for point in points]
    if all(points_inside):
        return "inside"

    parcel_edges = list(zip(parcel_ring, parcel_ring[1:]))
    for start, end in _geometry_segments(geometry):
        if any(_segments_intersect(start, end, parcel_start, parcel_end) for parcel_start, parcel_end in parcel_edges):
            return "partial"
    if geometry["type"] == "Polygon" and any(_point_in_polygon(point, geometry["coordinates"][0]) for point in parcel_ring[:-1]):
        return "partial"
    return "partial" if any(points_inside) else "outside"


def validate_parameters(object_type, parameters):
    definition = get_type_definition(object_type)
    if definition is None:
        raise ValidationError("Tipo de objeto desconhecido.")
    if not isinstance(parameters, dict):
        raise ValidationError("Os parâmetros têm de ser um objeto JSON.")
    schema = definition["parameter_schema"]
    unexpected = set(parameters) - set(schema)
    if unexpected:
        raise ValidationError("Parâmetros não definidos para este tipo: " + ", ".join(sorted(unexpected)))
    for name, rule in schema.items():
        if rule.get("required") and name not in parameters:
            raise ValidationError(f"O parâmetro '{name}' é obrigatório.")
        if name not in parameters:
            continue
        value = parameters[name]
        if rule.get("type") == "number" and (not isinstance(value, Real) or isinstance(value, bool)):
            raise ValidationError(f"O parâmetro '{name}' tem de ser numérico.")
        if rule.get("type") == "integer" and (
            not isinstance(value, Real) or isinstance(value, bool) or not float(value).is_integer()
        ):
            raise ValidationError(f"O parâmetro '{name}' tem de ser um número inteiro.")
        if rule.get("type") == "string" and not isinstance(value, str):
            raise ValidationError(f"O parâmetro '{name}' tem de ser texto.")
        if "minimum" in rule and value < rule["minimum"]:
            raise ValidationError(f"O parâmetro '{name}' tem de ser igual ou superior a {rule['minimum']}.")
        if "maximum" in rule and value > rule["maximum"]:
            raise ValidationError(f"O parâmetro '{name}' tem de ser igual ou inferior a {rule['maximum']}.")
        if "enum" in rule and value not in rule["enum"]:
            raise ValidationError(f"O parâmetro '{name}' não tem um valor permitido.")


def validate_project_object(object_type, geometry, parameters, base_parcel_geometry):
    definition = get_type_definition(object_type)
    if definition is None:
        raise ValidationError("Tipo de objeto desconhecido.")
    validate_geometry(geometry, definition["allowed_geometry_types"])
    validate_parameters(object_type, parameters)
    status = containment_status(geometry, base_parcel_geometry)
    if status == "outside" and not definition.get("allow_outside_parcel", False):
        raise ValidationError("A geometria está totalmente fora da BaseParcel.")
    return ["A geometria está parcialmente fora da BaseParcel."] if status == "partial" else []
