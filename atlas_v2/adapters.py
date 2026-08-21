"""Phase 2 adapter boundary between V2 contracts and preserved V1 engines."""

import motor_terraplanagem
import motor_agricultura
import motor_hidrico
import motor_solar

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

    def execute(self, terrain_context, scenario_object, parameters):
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


class CultivableAreaAdapter:
    """Adapter for the V1 agricultural area calculation, without changing the engine."""

    engine_type = "cultivable_area"

    def validate_input(self, scenario_object, parameters):
        if scenario_object["type"] != "crop_area":
            raise ValidationError("O motor de área cultivável requer um objeto do tipo crop_area.")
        validate_geometry(scenario_object["geometry"], ["Polygon"])
        validate_parameters(scenario_object["type"], parameters)

    @staticmethod
    def to_motor_input(geometry):
        return [(point[1], point[0]) for point in geometry["coordinates"][0][:-1]]

    def execute(self, terrain_context, scenario_object, parameters):
        terrain_clip = terrain_context.clip_for_geojson(scenario_object["geometry"])
        return motor_agricultura.calcular_area_cultivavel(
            terrain_clip, self.to_motor_input(scenario_object["geometry"])
        )

    @staticmethod
    def from_motor_output(output, scenario_object, parameters):
        sig_error = output.get("erro_sig")
        metrics = {key: output[key] for key in (
            "area_total_ha", "area_cultivavel_ha", "percentagem_cultivavel",
            "area_excluida_declive_ha", "area_excluida_ren_ha", "area_em_ran_ha",
            "declive_max_considerado_pct",
        )}
        return {
            "parameters_used": parameters,
            "status": "partial" if sig_error else "success",
            "metrics": metrics,
            "derived_geometries": [{"type": "Feature", "geometry": scenario_object["geometry"], "properties": {"role": "cultivable_area"}}],
            "warnings": [f"Não foi possível consultar RAN/REN: {sig_error}"] if sig_error else [],
            "errors": [],
            "limitations": [
                "Exclui apenas declive acima do limite considerado e REN; não considera construções, acessos ou outras condicionantes.",
                "RAN é apresentada como informação e não é excluída da área cultivável.",
                "Baseado em MDT LiDAR de 2 m; adequado a triagem, não a decisão agronómica final.",
            ],
        }


def polygon_centroid(geometry):
    """Return the WGS84 centroid of a simple GeoJSON polygon."""
    ring = geometry["coordinates"][0]
    double_area = centroid_x = centroid_y = 0.0
    for first, second in zip(ring, ring[1:]):
        cross = first[0] * second[1] - second[0] * first[1]
        double_area += cross
        centroid_x += (first[0] + second[0]) * cross
        centroid_y += (first[1] + second[1]) * cross
    if double_area:
        return centroid_y / (3 * double_area), centroid_x / (3 * double_area)
    return ring[0][1], ring[0][0]


class SolarPotentialAdapter:
    engine_type = "solar_potential"
    requires_terrain = False

    def validate_input(self, scenario_object, parameters):
        if scenario_object["type"] != "zone":
            raise ValidationError("O motor solar requer um objeto do tipo zone.")
        validate_geometry(scenario_object["geometry"], ["Polygon"])
        validate_parameters(scenario_object["type"], parameters)

    def execute(self, terrain_context, scenario_object, parameters):
        lat, lon = polygon_centroid(scenario_object["geometry"])
        return motor_solar.montar_conclusao(lat, lon, peakpower=parameters.get("peakpower_kw", 1.0))

    @staticmethod
    def from_motor_output(output, scenario_object, parameters):
        answer = output.get("answer")
        if not answer:
            reason = output.get("confidence", {}).get("reason", "Não foi possível concluir a análise solar.")
            return {"parameters_used": parameters, "status": "error", "metrics": {}, "derived_geometries": [], "warnings": [], "errors": [reason], "limitations": output.get("limitations", [])}
        best = answer["melhor_caso"]
        terrain = answer.get("terreno_real") or {}
        return {
            "parameters_used": parameters,
            "status": "partial" if answer.get("terreno_real") is None else "success",
            "metrics": {
                "potential": best["potencial"],
                "specific_yield_kwh_kwp_year": best["producao_especifica_kwh_por_kwp_ano"],
                "annual_irradiation_kwh_m2": best["irradiacao_anual_kwh_m2"],
                "optimal_angle_degrees": best["angulo_otimo_graus"],
                "terrain_slope_degrees": terrain.get("declive_estimado_graus"),
                "terrain_yield_kwh_kwp_year": terrain.get("producao_estimada_kwh_por_kwp_ano"),
            },
            "derived_geometries": [{"type": "Feature", "geometry": scenario_object["geometry"], "properties": {"role": "solar_zone"}}],
            "warnings": [] if answer.get("terreno_real") else ["Não foi possível estimar o declive e a orientação do terreno."],
            "errors": [],
            "limitations": output.get("limitations", []),
        }


class WaterContextAdapter:
    engine_type = "water_context"
    requires_terrain = False

    def validate_input(self, scenario_object, parameters):
        if scenario_object["type"] != "zone":
            raise ValidationError("O motor hídrico requer um objeto do tipo zone.")
        validate_geometry(scenario_object["geometry"], ["Polygon"])
        validate_parameters(scenario_object["type"], parameters)

    def execute(self, terrain_context, scenario_object, parameters):
        lat, lon = polygon_centroid(scenario_object["geometry"])
        return motor_hidrico.montar_conclusao(lat, lon)

    @staticmethod
    def from_motor_output(output, scenario_object, parameters):
        answer = output["answer"]
        return {
            "parameters_used": parameters,
            "status": "partial" if output.get("confidence", {}).get("label") == "Baixa" else "success",
            "metrics": {
                "surface_water_nearby": answer["indicadores_num_raio_1km"]["agua_superficie_perto"],
                "groundwater_capture_nearby": answer["indicadores_num_raio_1km"]["captacao_subterranea_perto"],
                "irrigation_infrastructure_nearby": answer["indicadores_num_raio_1km"]["infraestrutura_rega_perto"],
                "annual_precipitation_mm": answer["precipitacao_media_mm_ano"],
                "aquifer": (answer.get("sistema_aquifero") or {}).get("nome"),
                "water_points_nearby": answer["pontos_agua_subterranea"]["total_no_raio"],
            },
            "derived_geometries": [{"type": "Feature", "geometry": scenario_object["geometry"], "properties": {"role": "water_context_zone"}}],
            "warnings": [],
            "errors": [],
            "limitations": output.get("limitations", []),
        }


ADAPTERS = {
    EarthworkAdapter.engine_type: EarthworkAdapter(),
    CultivableAreaAdapter.engine_type: CultivableAreaAdapter(),
    SolarPotentialAdapter.engine_type: SolarPotentialAdapter(),
    WaterContextAdapter.engine_type: WaterContextAdapter(),
}
