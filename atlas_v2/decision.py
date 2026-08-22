"""Explainable, non-persistent Phase 5C comparison of existing scenarios."""


STATUS_LABELS = {
    "green": "Favorável para estudo preliminar",
    "yellow": "Requer atenção ou validação adicional",
    "red": "Risco ou conflito relevante nos dados disponíveis",
    "gray": "Dados insuficientes ou análise indisponível",
}


def _dimension(status, reason, data, limitations, action, sources=None):
    return {
        "status": status,
        "label": STATUS_LABELS[status],
        "reason": reason,
        "data": data,
        "limitations": limitations,
        "recommended_action": action,
        "sources": sources or [],
    }


def _objective_dimension(objects):
    buildings = [item for item in objects if item["type"] == "building"]
    if not buildings:
        return _dimension(
            "gray", "Esta alternativa ainda não contém uma implantação de edifício.",
            [], ["A adequação ao objetivo não é inferida sem uma geometria de implantação."],
            "Cria ou copia uma implantação antes de comparar esta dimensão.",
        )
    building_ids = {item["id"] for item in buildings}
    platforms = [item for item in objects if item["type"] == "platform" and item["parameters"].get("building_object_id") in building_ids]
    accesses = [item for item in objects if item["type"] == "access" and item["parameters"].get("building_object_id") in building_ids]
    complete = bool(platforms and accesses)
    status = "green" if complete else "yellow"
    missing = [label for present, label in ((platforms, "plataforma"), (accesses, "acesso inicial")) if not present]
    reason = (
        "A alternativa contém implantação, plataforma e acesso inicial editáveis."
        if complete else f"A implantação existe, mas falta {', '.join(missing)} no percurso preliminar."
    )
    return _dimension(
        status, reason,
        [
            {"label": "Edifícios", "value": len(buildings)},
            {"label": "Plataformas associadas", "value": len(platforms)},
            {"label": "Acessos associados", "value": len(accesses)},
        ],
        ["A existência destes objetos não demonstra viabilidade construtiva, acesso legal ou conformidade."],
        "Confirma programa, implantação, acessos e requisitos aplicáveis com os profissionais competentes.",
        ["Objetos persistidos da alternativa Atlas"],
    )


def _earthwork_dimension(objects, results):
    platforms = {item["id"]: item for item in objects if item["type"] == "platform"}
    candidates = [
        result for result in results
        if result["engine_type"] == "earthwork" and result["scenario_object_id"] in platforms
    ]
    current = [result for result in candidates if not result.get("is_stale") and result.get("status") in ("success", "partial")]
    if not current:
        stale = any(result.get("is_stale") for result in candidates)
        reason = (
            "Existe uma estimativa de terraplanagem desatualizada, que não foi usada na avaliação."
            if stale else "Não existe uma estimativa atual de terraplanagem para as plataformas desta alternativa."
        )
        return _dimension(
            "gray", reason, [],
            ["Resultados inexistentes, falhados ou stale não são convertidos numa indicação favorável/desfavorável."],
            "Calcula novamente a terraplanagem da plataforma atual.",
            ["Adapter V2 do motor V1 de terraplanagem"],
        )
    cut = sum(float(result["metrics"].get("volume_corte_m3") or 0) for result in current)
    fill = sum(float(result["metrics"].get("volume_aterro_m3") or 0) for result in current)
    area = sum(float(result["metrics"].get("area_total_m2") or 0) for result in current)
    movement = cut + fill
    intensity = movement / area if area else None
    if intensity is None:
        status, reason = "gray", "A estimativa não contém área suficiente para relacionar o volume movimentado."
    elif intensity <= 0.5:
        status, reason = "green", "A movimentação estimada é relativamente baixa face à área das plataformas."
    elif intensity <= 1.5:
        status, reason = "yellow", "A movimentação estimada requer atenção e confirmação topográfica."
    else:
        status, reason = "red", "A movimentação estimada é elevada face à área das plataformas."
    return _dimension(
        status, reason,
        [
            {"label": "Corte estimado", "value": round(cut, 1), "unit": "m³"},
            {"label": "Aterro estimado", "value": round(fill, 1), "unit": "m³"},
            {"label": "Movimento/área", "value": round(intensity, 2) if intensity is not None else None, "unit": "m³/m²"},
        ],
        list(dict.fromkeys(limit for result in current for limit in result.get("limitations", [])))[:4] + [
            "As classes usam uma heurística de triagem de 0,5 e 1,5 m³/m²; não são limites regulamentares ou de projeto."
        ],
        "Confirma cotas e volumes com levantamento topográfico e estudo técnico de terraplanagem.",
        ["MDT LiDAR 2 m", "Adapter V2 do motor V1 de terraplanagem"],
    )


def _terrain_dimension(objects, terrain_context):
    buildings = [item for item in objects if item["type"] == "building"]
    if not buildings or terrain_context is None:
        return _dimension(
            "gray", "Não existem implantação e dados de terreno suficientes para esta avaliação.", [],
            ["Sem uma geometria e cobertura MDT não é inferido um estado de relevo."],
            "Confirma a implantação e a cobertura do MDT.", ["MDT LiDAR disponível no Atlas"],
        )
    try:
        statistics = [terrain_context.geometry_statistics(item["geometry"]) for item in buildings]
    except (ValueError, FileNotFoundError):
        return _dimension(
            "gray", "Não foi possível obter estatísticas de relevo para a implantação.", [],
            ["A geometria pode ser demasiado pequena ou estar fora da cobertura do MDT."],
            "Valida a cobertura e confirma o relevo através de levantamento topográfico.", ["MDT LiDAR disponível no Atlas"],
        )
    median_slope = sum(item["slope_median_percent"] for item in statistics) / len(statistics)
    max_slope = max(item["slope_max_percent"] for item in statistics)
    elevation_range = max(item["elevation_range_m"] for item in statistics)
    if median_slope <= 8:
        status, reason = "green", "O declive mediano aparente da implantação é baixo no MDT disponível."
    elif median_slope <= 18:
        status, reason = "yellow", "O declive mediano aparente requer atenção no desenvolvimento da implantação."
    else:
        status, reason = "red", "O declive mediano aparente é elevado na área da implantação."
    return _dimension(
        status, reason,
        [
            {"label": "Declive mediano", "value": round(median_slope, 1), "unit": "%"},
            {"label": "Declive máximo amostrado", "value": round(max_slope, 1), "unit": "%"},
            {"label": "Amplitude de cotas", "value": round(elevation_range, 1), "unit": "m"},
        ],
        [
            "O declive deriva do MDT e não avalia estabilidade geotécnica, solo ou capacidade de fundação.",
            "As classes usam uma heurística de triagem de 8% e 18%; não são limites regulamentares.",
        ],
        "Confirma o terreno com levantamento topográfico e avaliação geotécnica adequada.",
        ["MDT LiDAR 2 m"],
    )


def _constraints_dimension(objects, results):
    building_ids = {item["id"] for item in objects if item["type"] == "building"}
    candidates = [
        result for result in results
        if result["engine_type"] == "site_constraints" and result["scenario_object_id"] in building_ids
    ]
    current = [result for result in candidates if not result.get("is_stale") and result.get("status") in ("success", "partial")]
    if not current:
        stale = any(result.get("is_stale") for result in candidates)
        return _dimension(
            "gray",
            "A consulta de condicionantes está desatualizada e não foi usada." if stale else "As condicionantes ainda não foram consultadas para esta implantação.",
            [], ["Ausência de resultado não significa ausência de condicionantes."],
            "Executa a consulta e confirma sempre as camadas e regras junto das entidades competentes.",
            ["SIG municipal de Silves"],
        )
    constraint_count = sum(int(result["metrics"].get("constraint_count") or 0) for result in current)
    risk_count = sum(int(result["metrics"].get("risk_count") or 0) for result in current)
    partial = any(result.get("status") == "partial" for result in current)
    if constraint_count or risk_count:
        status = "red"
        reason = "Foram identificadas condicionantes ou riscos nas camadas consultadas."
    elif partial:
        status = "yellow"
        reason = "Não foram identificados conflitos, mas uma ou mais fontes devolveram informação incompleta."
    else:
        status = "green"
        reason = "Não foram identificadas condicionantes ou riscos nas camadas consultadas para o ponto da implantação."
    constraints = list(dict.fromkeys(value for result in current for value in result["metrics"].get("active_constraints", [])))
    risks = list(dict.fromkeys(value for result in current for value in result["metrics"].get("identified_risks", [])))
    sources = list(dict.fromkeys(source for result in current for source in result["metrics"].get("sources", [])))
    return _dimension(
        status, reason,
        [
            {"label": "Condicionantes identificadas", "value": constraint_count},
            {"label": "Riscos identificados", "value": risk_count},
            {"label": "Fichas", "value": constraints + risks},
        ],
        list(dict.fromkeys(limit for result in current for limit in result.get("limitations", [])))[:6],
        "Consulta o PDM e as entidades competentes; uma camada cartográfica não decide licenciamento ou viabilidade.",
        sources,
    )


def compare_scenario(scenario, results, terrain_context):
    dimensions = {
        "objective": _objective_dimension(scenario["objects"]),
        "earthwork": _earthwork_dimension(scenario["objects"], results),
        "terrain": _terrain_dimension(scenario["objects"], terrain_context),
        "constraints": _constraints_dimension(scenario["objects"], results),
    }
    advantages = [value["reason"] for value in dimensions.values() if value["status"] == "green"]
    concerns = [value["reason"] for value in dimensions.values() if value["status"] in ("yellow", "red")]
    missing = [value["reason"] for value in dimensions.values() if value["status"] == "gray"]
    return {
        "scenario_id": scenario["id"],
        "scenario_name": scenario["name"],
        "dimensions": dimensions,
        "advantages": advantages,
        "concerns": concerns,
        "missing_information": missing,
        "object_count": len(scenario["objects"]),
    }


def compare_scenarios(scenarios, results_by_scenario, terrain_context):
    return {
        "objective": "Comparar alternativas de implantação de edifício",
        "scenarios": [
            compare_scenario(scenario, results_by_scenario.get(scenario["id"], []), terrain_context)
            for scenario in scenarios
        ],
        "status_legend": STATUS_LABELS,
        "disclaimer": (
            "Comparação para estudo preliminar. As cores não representam aprovação, conformidade legal, "
            "segurança de execução ou parecer profissional."
        ),
        "method": {
            "version": "phase5c-v1",
            "dimensions": ["objective", "earthwork", "terrain", "constraints"],
            "persistent": False,
            "ranking": False,
        },
    }
