"""
Atlas - Motor de Planeamento Agricola v0

Tres funcionalidades, deliberadamente limitadas a Nivel 1/2 (nunca Nivel 3):
  1. Area cultivavel real dentro de um poligono (exclui declive excessivo e REN).
  2. Necessidades de rega de uma cultura à escolha do utilizador, pela
     metodologia FAO-56 (ET0 x Kc - precipitacao efetiva).
  3. Compatibilidade solo/clima vs. cultura -- compara o que ja medimos
     (pH, textura, precipitacao) contra intervalos publicados, sem prever
     producao nem recomendar o que plantar.

O Atlas NUNCA recomenda uma cultura, nunca estima producao/rendimento, nunca
faz projecao economica -- a cultura e sempre escolhida pelo utilizador.
"""

import json
import math
import urllib.request
import urllib.parse
from datetime import datetime, timezone, date
import numpy as np

from motor_charca import _obter_mosaico, TIF_NORTE_DEFAULT, TIF_SUL_DEFAULT
from motor_terraplanagem import _pontos_dentro_poligono
import motor_agricola

BASE_URL = "https://sigeo.cm-silves.pt/arcgis/rest/services/PDM_MS/MapServer"
RAN_LAYER_ID = 406
REN_LAYER_ID = 399
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"

DECLIVE_MAX_PADRAO = 25.0  # % -- limite comum p/ mecanizacao agricola tradicional

# Valores aproximados, baseados em curvas Kc publicadas (FAO Irrigation and
# Drainage Paper 56) e literatura agronomica regional para o Mediterraneo --
# NAO calibrados localmente. Ver limitations nas respostas.
CULTURAS = {
    "olival": {
        "nome": "Olival",
        "kc_mensal": [0.5, 0.5, 0.55, 0.6, 0.65, 0.7, 0.65, 0.6, 0.6, 0.55, 0.5, 0.5],
        "ph_min": 6.0, "ph_max": 8.5,
        "texturas_preferidas": ["Franco", "Franco-argiloso", "Franco-arenoso", "Areia-franca"],
        "precip_min_mm": 300, "precip_max_mm": 800,
    },
    "vinha": {
        "nome": "Vinha",
        "kc_mensal": [0.3, 0.3, 0.35, 0.45, 0.6, 0.7, 0.7, 0.65, 0.55, 0.4, 0.3, 0.3],
        "ph_min": 5.5, "ph_max": 7.5,
        "texturas_preferidas": ["Franco-arenoso", "Areia-franca", "Franco"],
        "precip_min_mm": 400, "precip_max_mm": 800,
    },
    "amendoal": {
        "nome": "Amendoal",
        "kc_mensal": [0.4, 0.4, 0.5, 0.65, 0.8, 0.95, 1.0, 0.9, 0.75, 0.6, 0.45, 0.4],
        "ph_min": 6.0, "ph_max": 8.0,
        "texturas_preferidas": ["Franco-arenoso", "Areia-franca", "Franco"],
        "precip_min_mm": 300, "precip_max_mm": 700,
    },
    "citrinos": {
        "nome": "Citrinos",
        "kc_mensal": [0.65, 0.65, 0.65, 0.7, 0.7, 0.75, 0.75, 0.75, 0.7, 0.7, 0.65, 0.65],
        "ph_min": 6.0, "ph_max": 7.5,
        "texturas_preferidas": ["Franco", "Franco-argiloso", "Franco-arenoso"],
        "precip_min_mm": 500, "precip_max_mm": 1000,
    },
    "horticolas_regadio": {
        "nome": "Hortícolas de regadio",
        "kc_mensal": [0.3, 0.3, 0.4, 0.6, 0.85, 1.05, 1.1, 1.0, 0.85, 0.6, 0.35, 0.3],
        "ph_min": 6.0, "ph_max": 7.0,
        "texturas_preferidas": ["Franco", "Franco-siltoso"],
        "precip_min_mm": 500, "precip_max_mm": 1200,
    },
    "cereais_sequeiro": {
        "nome": "Cereais de sequeiro",
        "kc_mensal": [0.4, 0.5, 0.7, 0.9, 1.0, 0.6, 0.15, 0.15, 0.15, 0.15, 0.2, 0.3],
        "ph_min": 5.5, "ph_max": 7.5,
        "texturas_preferidas": ["Franco", "Franco-argiloso", "Franco-siltoso"],
        "precip_min_mm": 350, "precip_max_mm": 700,
    },
    "pastagem": {
        "nome": "Pastagem / Prado",
        "kc_mensal": [0.7, 0.7, 0.75, 0.8, 0.85, 0.85, 0.8, 0.75, 0.75, 0.75, 0.7, 0.7],
        "ph_min": 5.5, "ph_max": 7.5,
        "texturas_preferidas": ["Franco", "Franco-argiloso", "Franco-siltoso", "Franco-arenoso"],
        "precip_min_mm": 500, "precip_max_mm": 1200,
    },
}

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


# ---------------------------------------------------------------------
# 1. Area cultivavel real (declive + REN)
# ---------------------------------------------------------------------
def _calcular_declive_grid(grid, pixel_m):
    dzdy, dzdx = np.gradient(grid, pixel_m)
    declive_rad = np.arctan(np.sqrt(dzdx**2 + dzdy**2))
    return np.tan(declive_rad) * 100  # percentagem


def _query_geometrias(layer_id, xmin, ymin, xmax, ymax):
    params = {
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "OBJECTID",
        "where": "1=1",
        "returnGeometry": "true",
        "f": "geojson",
    }
    url = f"{BASE_URL}/{layer_id}/query?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "AtlasPrototype/0.1"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("features", [])


def _mascara_de_features(mosaico, features, rows_grid, cols_grid):
    mascara = np.zeros(rows_grid.shape, dtype=bool)
    for f in features:
        geom = f.get("geometry")
        if not geom:
            continue
        aneis_exteriores = []
        if geom["type"] == "Polygon":
            aneis_exteriores = [geom["coordinates"][0]]
        elif geom["type"] == "MultiPolygon":
            aneis_exteriores = [parte[0] for parte in geom["coordinates"]]
        for anel in aneis_exteriores:
            anel_rc = [mosaico.latlon_para_pixel(lat, lon) for lon, lat in anel]
            mascara |= _pontos_dentro_poligono(rows_grid, cols_grid, anel_rc)
    return mascara


def calcular_area_cultivavel(mosaico, poligono_latlon, declive_max=DECLIVE_MAX_PADRAO):
    if len(poligono_latlon) < 3:
        raise ValueError("São necessários pelo menos 3 pontos para definir uma área.")

    poligono_rc = [mosaico.latlon_para_pixel(lat, lon) for lat, lon in poligono_latlon]
    for r, c in poligono_rc:
        if not mosaico.dentro(r, c):
            raise ValueError("Uma ou mais pontos do polígono caem fora da área coberta pelos ficheiros.")

    rows_poly = [p[0] for p in poligono_rc]
    cols_poly = [p[1] for p in poligono_rc]
    margem = 2
    r_min = max(0, min(rows_poly) - margem)
    r_max = min(mosaico.grid.shape[0] - 1, max(rows_poly) + margem)
    c_min = max(0, min(cols_poly) - margem)
    c_max = min(mosaico.grid.shape[1] - 1, max(cols_poly) + margem)

    rows_grid, cols_grid = np.mgrid[r_min:r_max + 1, c_min:c_max + 1]
    dentro_poligono = _pontos_dentro_poligono(rows_grid, cols_grid, poligono_rc)

    n_total = int(dentro_poligono.sum())
    if n_total == 0:
        raise ValueError("O polígono não cobre nenhuma célula de dados (é demasiado pequeno?).")

    declive_grid = _calcular_declive_grid(mosaico.grid, mosaico.pixel)[r_min:r_max + 1, c_min:c_max + 1]

    lats = [p[0] for p in poligono_latlon]
    lons = [p[1] for p in poligono_latlon]
    try:
        ren_features = _query_geometrias(REN_LAYER_ID, min(lons), min(lats), max(lons), max(lats))
        ran_features = _query_geometrias(RAN_LAYER_ID, min(lons), min(lats), max(lons), max(lats))
        mascara_ren = _mascara_de_features(mosaico, ren_features, rows_grid, cols_grid)
        mascara_ran = _mascara_de_features(mosaico, ran_features, rows_grid, cols_grid)
        erro_sig = None
    except Exception as e:
        mascara_ren = np.zeros_like(dentro_poligono)
        mascara_ran = np.zeros_like(dentro_poligono)
        erro_sig = str(e)

    declive_ok = declive_grid <= declive_max
    cultivavel = dentro_poligono & declive_ok & ~mascara_ren

    area_celula = mosaico.pixel ** 2
    area_total_m2 = n_total * area_celula
    area_cultivavel_m2 = int(cultivavel.sum()) * area_celula
    area_excluida_declive_m2 = int((dentro_poligono & ~declive_ok & ~mascara_ren).sum()) * area_celula
    area_excluida_ren_m2 = int((dentro_poligono & mascara_ren).sum()) * area_celula
    area_em_ran_m2 = int((dentro_poligono & mascara_ran).sum()) * area_celula

    return {
        "area_total_ha": round(area_total_m2 / 10000, 3),
        "area_cultivavel_ha": round(area_cultivavel_m2 / 10000, 3),
        "percentagem_cultivavel": round(100 * area_cultivavel_m2 / area_total_m2, 1) if area_total_m2 else 0,
        "area_excluida_declive_ha": round(area_excluida_declive_m2 / 10000, 3),
        "area_excluida_ren_ha": round(area_excluida_ren_m2 / 10000, 3),
        "area_em_ran_ha": round(area_em_ran_m2 / 10000, 3),
        "declive_max_considerado_pct": declive_max,
        "erro_sig": erro_sig,
    }


# ---------------------------------------------------------------------
# 2. Necessidades de rega (FAO-56: ETc = ET0 x Kc; rega = max(0, ETc - precip efetiva))
# ---------------------------------------------------------------------
def obter_et0_precipitacao_mensal(lat, lon, anos=10):
    ano_atual = date.today().year
    ano_fim = ano_atual - 1
    ano_inicio = ano_fim - anos + 1

    params = {
        "latitude": lat, "longitude": lon,
        "start_date": f"{ano_inicio}-01-01", "end_date": f"{ano_fim}-12-31",
        "daily": "et0_fao_evapotranspiration,precipitation_sum",
        "timezone": "auto",
    }
    url = f"{OPEN_METEO_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "AtlasPrototype/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    datas = data["daily"]["time"]
    et0_diario = data["daily"]["et0_fao_evapotranspiration"]
    precip_diario = data["daily"]["precipitation_sum"]

    et0_por_mes = [[] for _ in range(12)]
    precip_por_mes = [[] for _ in range(12)]
    for d, e, p in zip(datas, et0_diario, precip_diario):
        mes = int(d.split("-")[1]) - 1
        if e is not None:
            et0_por_mes[mes].append(e)
        if p is not None:
            precip_por_mes[mes].append(p)

    et0_mensal_mm = [round(sum(mes) / anos, 1) if mes else 0.0 for mes in et0_por_mes]
    precip_mensal_mm = [round(sum(mes) / anos, 1) if mes else 0.0 for mes in precip_por_mes]

    return et0_mensal_mm, precip_mensal_mm, ano_inicio, ano_fim


def calcular_necessidades_rega(lat, lon, cultura_id, area_ha):
    if cultura_id not in CULTURAS:
        raise ValueError(f"Cultura desconhecida: {cultura_id}")
    cultura = CULTURAS[cultura_id]
    area_m2 = area_ha * 10000

    et0_mensal, precip_mensal, ano_i, ano_f = obter_et0_precipitacao_mensal(lat, lon)

    linhas = []
    total_etc_mm = 0.0
    total_rega_mm = 0.0
    for i, mes in enumerate(MESES):
        etc_mm = et0_mensal[i] * cultura["kc_mensal"][i]
        precip_efetiva_mm = min(precip_mensal[i], etc_mm)
        rega_mm = max(0.0, etc_mm - precip_efetiva_mm)
        total_etc_mm += etc_mm
        total_rega_mm += rega_mm
        linhas.append({
            "mes": mes,
            "et0_mm": round(et0_mensal[i], 1),
            "kc": cultura["kc_mensal"][i],
            "etc_mm": round(etc_mm, 1),
            "precipitacao_mm": round(precip_mensal[i], 1),
            "rega_necessaria_mm": round(rega_mm, 1),
            "rega_necessaria_m3": round(rega_mm * area_m2 / 1000, 1),
        })

    return {
        "cultura": cultura["nome"],
        "area_ha": area_ha,
        "periodo_referencia": f"{ano_i}-{ano_f}",
        "linhas_mensais": linhas,
        "total_anual_etc_mm": round(total_etc_mm, 1),
        "total_anual_rega_mm": round(total_rega_mm, 1),
        "total_anual_rega_m3": round(total_rega_mm * area_m2 / 1000, 1),
    }


# ---------------------------------------------------------------------
# 3. Compatibilidade solo/clima vs. cultura (NUNCA producao/rendimento)
# ---------------------------------------------------------------------
def calcular_compatibilidade(lat, lon, cultura_id):
    if cultura_id not in CULTURAS:
        raise ValueError(f"Cultura desconhecida: {cultura_id}")
    cultura = CULTURAS[cultura_id]

    dados_solo = motor_agricola.consultar_soilgrids(lat, lon)
    props = motor_agricola.extrair_propriedades(dados_solo)
    clay, sand, silt = props.get("clay"), props.get("sand"), props.get("silt")
    ph = props.get("phh2o")
    textura = motor_agricola.classificar_textura(clay, sand, silt) if all(v is not None for v in (clay, sand, silt)) else None

    _, precip_mensal, ano_i, ano_f = obter_et0_precipitacao_mensal(lat, lon)
    precip_anual_mm = round(sum(precip_mensal), 1)

    avaliacoes = []

    if ph is not None:
        if cultura["ph_min"] <= ph <= cultura["ph_max"]:
            avaliacoes.append({"criterio": "pH do solo", "valor_medido": ph, "intervalo_publicado": f'{cultura["ph_min"]}–{cultura["ph_max"]}', "resultado": "Compatível"})
        else:
            avaliacoes.append({"criterio": "pH do solo", "valor_medido": ph, "intervalo_publicado": f'{cultura["ph_min"]}–{cultura["ph_max"]}', "resultado": "Fora do intervalo típico"})
    else:
        avaliacoes.append({"criterio": "pH do solo", "valor_medido": None, "intervalo_publicado": f'{cultura["ph_min"]}–{cultura["ph_max"]}', "resultado": "Sem dados"})

    if textura is not None:
        if textura in cultura["texturas_preferidas"]:
            avaliacoes.append({"criterio": "Textura do solo", "valor_medido": textura, "intervalo_publicado": ", ".join(cultura["texturas_preferidas"]), "resultado": "Compatível"})
        else:
            avaliacoes.append({"criterio": "Textura do solo", "valor_medido": textura, "intervalo_publicado": ", ".join(cultura["texturas_preferidas"]), "resultado": "Fora das texturas típicas"})
    else:
        avaliacoes.append({"criterio": "Textura do solo", "valor_medido": None, "intervalo_publicado": ", ".join(cultura["texturas_preferidas"]), "resultado": "Sem dados"})

    if cultura["precip_min_mm"] <= precip_anual_mm <= cultura["precip_max_mm"]:
        resultado_precip = "Compatível (sem contar com rega)"
    elif precip_anual_mm < cultura["precip_min_mm"]:
        resultado_precip = "Abaixo do típico -- provavelmente precisa de rega"
    else:
        resultado_precip = "Acima do típico"
    avaliacoes.append({
        "criterio": "Precipitação anual", "valor_medido": precip_anual_mm,
        "intervalo_publicado": f'{cultura["precip_min_mm"]}–{cultura["precip_max_mm"]} mm',
        "resultado": resultado_precip,
    })

    n_compativel = sum(1 for a in avaliacoes if a["resultado"] == "Compatível" or "Compatível" in a["resultado"])

    return {
        "cultura": cultura["nome"],
        "avaliacoes": avaliacoes,
        "resumo": f"{n_compativel} de {len(avaliacoes)} critérios compatíveis",
        "periodo_referencia_precipitacao": f"{ano_i}-{ano_f}",
    }


def montar_conclusao_area_cultivavel(poligono_latlon, path_norte=TIF_NORTE_DEFAULT, path_sul=TIF_SUL_DEFAULT):
    try:
        mosaico = _obter_mosaico(path_norte, path_sul)
        resultado = calcular_area_cultivavel(mosaico, poligono_latlon)
    except Exception as e:
        return _erro("AreaCultivavel", "Quanta área desta zona é realmente cultivável?", str(e))

    limitations = [
        "Exclui apenas declive acima do limite considerado (25% por omissão) e REN -- "
        "não considera construções existentes, acessos, nem outras condicionantes.",
        "RAN não é excluída (é solo reservado PARA agricultura, não uma restrição a ela) "
        "-- é mostrada só como informação.",
    ]
    if resultado.get("erro_sig"):
        limitations.insert(0, f"Não foi possível confirmar RAN/REN: {resultado['erro_sig']}")

    return {
        "engine": "AreaCultivavel",
        "question": "Quanta área desta zona é realmente cultivável?",
        "answer": resultado,
        "knowledge_level": "INFERENCE",
        "confidence": {"label": "Média", "reason": "Baseado em declive do MDT LiDAR (2m) e condicionantes legais oficiais."},
        "limitations": limitations,
        "sources": ["DGT -- LiDAR (2m)", "sigeo.cm-silves.pt (PDM_MS)"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def montar_conclusao_rega(lat, lon, cultura_id, area_ha):
    try:
        resultado = calcular_necessidades_rega(lat, lon, cultura_id, area_ha)
    except Exception as e:
        return _erro("NecessidadesRega", "Quanta água esta cultura precisa, nesta área?", str(e))

    return {
        "engine": "NecessidadesRega",
        "question": "Quanta água esta cultura precisa, nesta área?",
        "answer": resultado,
        "knowledge_level": "INFERENCE",
        "confidence": {
            "label": "Média",
            "reason": "Metodologia FAO-56 (ET0 x Kc), com ET0 do Open-Meteo e Kc de tabelas publicadas -- não calibrado localmente.",
        },
        "limitations": [
            "Valores de Kc são aproximações regionais publicadas, não medições feitas nesta parcela.",
            "Precipitação efetiva estimada de forma simplificada (não conta com escorrência, tipo de solo, ou armazenamento profundo).",
            "Não inclui eficiência do sistema de rega (gota-a-gota vs. aspersão têm perdas diferentes) nem custo da água.",
            "É uma estimativa técnica (Nível 2) -- não é projeção económica nem garantia de produção.",
        ],
        "sources": ["https://open-meteo.com (ET0 FAO Penman-Monteith)", "FAO Irrigation and Drainage Paper 56"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def montar_conclusao_compatibilidade(lat, lon, cultura_id):
    try:
        resultado = calcular_compatibilidade(lat, lon, cultura_id)
    except Exception as e:
        return _erro("Compatibilidade", "Esta cultura é compatível com o solo/clima medidos aqui?", str(e))

    return {
        "engine": "Compatibilidade",
        "question": "Esta cultura é compatível com o solo/clima medidos aqui?",
        "answer": resultado,
        "knowledge_level": "INFERENCE",
        "confidence": {
            "label": "Média",
            "reason": "Compara medições reais (SoilGrids, Open-Meteo) contra intervalos publicados -- não é um modelo de aptidão calibrado.",
        },
        "limitations": [
            "NÃO prevê produção, rendimento, ou retorno de investimento -- só compatibilidade técnica de solo/clima.",
            "Solo medido por modelo global (SoilGrids, 250m) -- não substitui uma análise de solo real.",
            "Não considera microclima, exposição solar, drenagem local, nem variedades/cultivares específicas.",
        ],
        "sources": ["https://www.isric.org (SoilGrids)", "https://open-meteo.com", "FAO -- requisitos publicados por cultura"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _erro(engine, question, motivo):
    return {
        "engine": engine, "question": question, "answer": None,
        "knowledge_level": "INFERENCE",
        "confidence": {"label": "Baixa", "reason": motivo},
        "limitations": [motivo],
        "sources": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
