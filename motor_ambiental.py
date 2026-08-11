"""
Atlas - Motor Ambiental v0

Cobre:
  1. Classificacao de risco de incendio da parcela (SIG de Silves).
  2. Historico de incendios florestais na zona (SIG de Silves).
  3. Obrigacao legal de gestao de combustivel -- 50m se a classificacao de
     solo for florestal, 10m se for agricola, conforme o Decreto-Lei
     82/2021 (Sistema de Gestao Integrada de Fogos Rurais), atualizado
     pelo Decreto-Lei 6/2025. Reaproveita a classificacao de solo que o
     Motor Juridico ja calcula.
  4. Distancia a estrada mais proxima (SIG de Silves) -- informacao de
     acesso, NAO uma rota de fuga.

O que este motor explicitamente NAO faz: nao gera uma rota de evacuacao
dinamica, nem substitui o Plano Municipal de Emergencia de Protecao Civil.
Em caso de incendio real, o numero e sempre o 112.
"""

import json
import math
from datetime import datetime, timezone
import urllib.request
import urllib.parse

import motor_juridico

BASE_URL = "https://sigeo.cm-silves.pt/arcgis/rest/services/PDM_MS/MapServer"
RISCO_INCENDIO_LAYER_ID = 409
HISTORICO_INCENDIO_LAYER_ID = 408
REDE_RODOVIARIA_LAYER_ID = 372

FAIXA_FLORESTAL_M = 50
FAIXA_AGRICOLA_M = 10


def _query_layer_buffer(layer_id, lat, lon, raio_m):
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": raio_m,
        "units": "esriSRUnit_Meter",
        "outFields": "*",
        "where": "1=1",
        "returnGeometry": "false",
        "f": "json",
    }
    url = f"{BASE_URL}/{layer_id}/query?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "AtlasPrototype/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    features = data.get("features", [])
    return [f for f in features if f.get("attributes", {}).get("DESACTIVO") not in (1, "1")]


def _query_layer_ponto(layer_id, lat, lon):
    return _query_layer_buffer(layer_id, lat, lon, raio_m=1)


def obter_classe_risco_incendio(lat, lon):
    features = _query_layer_ponto(RISCO_INCENDIO_LAYER_ID, lat, lon)
    if not features:
        return None
    return features[0]["attributes"]


def obter_historico_incendios(lat, lon):
    features = _query_layer_ponto(HISTORICO_INCENDIO_LAYER_ID, lat, lon)
    return len(features) > 0


def obter_distancia_estrada(lat, lon, raio_inicial_m=200, raio_max_m=2000):
    raio = raio_inicial_m
    while raio <= raio_max_m:
        features = _query_layer_buffer(REDE_RODOVIARIA_LAYER_ID, lat, lon, raio)
        if features:
            return raio
        raio *= 2
    return None


def determinar_faixa_gestao_combustivel(classificacao_solo):
    if classificacao_solo and "Florestal" in classificacao_solo:
        return FAIXA_FLORESTAL_M, "florestal"
    return FAIXA_AGRICOLA_M, "agrícola/outro"


def montar_conclusao(lat, lon):
    limitations = [
        "Este motor NÃO gera uma rota de evacuação dinâmica -- isso depende "
        "de condições em tempo real (vento, propagação do fogo, estradas "
        "cortadas) que exigem comando no terreno pela Proteção Civil/GNR/"
        "bombeiros, não um cálculo estático.",
        "Não substitui o Plano Municipal de Emergência de Proteção Civil. "
        "Em caso de incêndio real, liga sempre 112.",
        "A distância à estrada é uma aproximação por procura em anéis "
        "concêntricos -- não é a distância exata a pé nem por estrada.",
    ]

    try:
        classe_risco = obter_classe_risco_incendio(lat, lon)
    except Exception as e:
        classe_risco = None
        limitations.insert(0, f"Não foi possível obter a classe de risco de incêndio: {e}")

    try:
        ja_ardeu = obter_historico_incendios(lat, lon)
    except Exception as e:
        ja_ardeu = None
        limitations.insert(0, f"Não foi possível obter o histórico de incêndios: {e}")

    try:
        distancia_estrada_m = obter_distancia_estrada(lat, lon)
    except Exception as e:
        distancia_estrada_m = None
        limitations.insert(0, f"Não foi possível calcular a distância à estrada: {e}")

    try:
        juridico = motor_juridico.montar_conclusao(lat, lon)
        classificacao_solo = juridico["answer"]["classificacao_solo"]
    except Exception as e:
        classificacao_solo = None
        limitations.insert(0, f"Não foi possível obter a classificação de solo: {e}")

    faixa_m, tipo_faixa = determinar_faixa_gestao_combustivel(classificacao_solo)

    return {
        "engine": "Ambiental",
        "question": "Que riscos ambientais existem, e que obrigações legais de segurança se aplicam?",
        "coordinates": {"lat": lat, "lon": lon},
        "answer": {
            "classe_risco_incendio": classe_risco.get("DESIGNACAO_PO") if classe_risco else "Não determinada",
            "ja_ardeu_historicamente": ja_ardeu,
            "distancia_estrada_mais_proxima_m": distancia_estrada_m,
            "faixa_gestao_combustivel": {
                "distancia_m": faixa_m,
                "tipo_solo_considerado": tipo_faixa,
                "base_legal": "Decreto-Lei 82/2021 (Sistema de Gestão Integrada de Fogos Rurais), atualizado pelo Decreto-Lei 6/2025",
            },
        },
        "knowledge_level": "FACT",
        "confidence": {
            "label": "Média",
            "reason": "Classe de risco e histórico vêm do SIG oficial de Silves; a faixa de gestão de combustível é uma obrigação legal geral aplicada à classificação de solo local.",
        },
        "limitations": limitations,
        "sources": [
            "sigeo.cm-silves.pt/arcgis/rest/services/PDM_MS/MapServer",
            "Decreto-Lei 82/2021 e Decreto-Lei 6/2025 (Diário da República)",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
