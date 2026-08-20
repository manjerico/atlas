"""Phase 2 adapter boundary between V2 contracts and preserved V1 engines."""

import motor_terraplanagem

from .validation import ValidationError, validate_geometry, validate_parameters


class EarthworkAdapter:
    engine_type = "earthwork"

    def validate_input(self, scenario_object, parameters):
        if scenario_object["type"] != "platform":
            raise ValidationError("O motor de terraplanagem requer um objeto do tipo platform.")
        validate_geometry(scenario_object["geometry"], ["Polygon"])
        validate_parameters(scenario_object["type"], parameters)

    @staticmethod
    def to_motor_input(geometry):
        return [(point[1], point[0]) for point in geometry["coordinates"][0][:-1]]

    def execute(self, terrain_context, scenario_object):
        terrain_clip = terrain_context.clip_for_geojson(scenario_object["geometry"])
        return motor_terraplanagem.calcular_terraplanagem(terrain_clip, self.to_motor_input(scenario_object["geometry"]))

    @staticmethod
    def from_motor_output(output, scenario_object, parameters):
        return {
            "parameters_used": parameters,
            "status": "success",
            "metrics": {key: output[key] for key in ("cota_alvo_m", "area_total_m2", "area_total_ha", "volume_corte_m3", "volume_aterro_m3", "saldo_m3")},
            "derived_geometries": [{"type": "Feature", "geometry": scenario_object["geometry"], "properties": {"role": "earthwork_area"}}],
            "warnings": [],
            "errors": [],
            "limitations": [
                "Cota-alvo definida pela média das cotas da área.",
                "Não inclui empolamento, compactação, custos ou levantamento topográfico de obra.",
                "Baseado em MDT LiDAR de 2 m; adequado a triagem, não a orçamento final.",
            ],
        }


ADAPTERS = {EarthworkAdapter.engine_type: EarthworkAdapter()}
