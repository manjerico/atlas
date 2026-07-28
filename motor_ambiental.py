"""
Atlas - Motor Ambiental v0

Cobre:
  1. Classificacao de risco de incendio (SIG de Silves)
  2. Historico de incendios florestais
  3. Obrigacao legal de gestao de combustivel -- faixa de 50m (territorio
     florestal) ou 10m (territorio agricola) a volta de edificacoes,
     conforme o Decreto-Lei n.º 82/2021 (Sistema de Gestao Integrada de
     Fogos Rurais), atualizado pelo Decreto-Lei n.º 6/2025
  4. Distancia a estrada mais proxima

O que este motor DELIBERADAMENTE NAO faz: nao gera uma rota de fuga
dinamica para um incendio real. Isso exige informacao em tempo real
(vento, velocidade de propagacao, cortes de estrada) e comando no terreno
-- e da responsabilidade da Protecao Civil, GNR e bombeiros, nao de um
calculo estatico sobre um mapa feito de antemao. EM CASO DE INCENDIO
REAL: LIGUE 112.
"""

import json
import math
from datetime import datetime, timezone
import urllib.request
import urllib.parse

BASE_URL = "https://sigeo.cm-silves.pt/arcgis/rest/services/PDM_MS/MapServer"

LAYER_RISCO_INCENDIO = 409
LAYER_INCENDIOS_HISTORICO = 408
LAYER_SOLO = 465
LAYER_ESTRADAS = 372


def _query_ponto(layer_id, lat, lon):
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
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


def _query_estradas_proximas(lat, lon, raio_m=3000):
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": raio_m,
        "units": "esriSRUnit_Meter",
        "outFields": "OBJECTID",
        "where": "1=1",
        "returnGeometry": "true",
        "f": "geojson",
    }
    url = f"{BASE_URL}/{LAYER_ESTRADAS}/query?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "AtlasPrototype/0.1"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _distancia_m(lat1, lon1, lat2, lon2):
    """Distancia aproximada em metros (formula equiretangular -- suficiente
    para as distancias curtas aqui em causa, nao para navegacao)."""
    R = 6371000
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return math.sqrt(x * x + y * y) * R


def _distancia_estrada_mais_proxima(lat, lon):
    geo = _query_estradas_proximas(lat, lon)
    features = geo.get("features", [])
    if not features:
        return None
    menor_dist = None
    for f in features:
        geom = f.get("geometry")
        if not geom:
            continue
        coords = geom["coordinates"]
        if geom["type"] == "MultiLineString":
            todos_pontos = [pt for parte in coords for pt in parte]
        else:
            todos_pontos = coords
        for lon_v, lat_v in todos_pontos:
            d = _distancia_m(lat, lon, lat_v, lon_v)
            if menor_dist is None or d < menor_dist:
                menor_dist = d
    return menor_dist


def montar_conclusao(lat, lon):
    limitations = [
        "NÃO gera uma rota de fuga dinâmica -- um incêndio real muda com o "
        "vento e a propagação em tempo real, e exige comando no terreno. "
        "Segue sempre a Proteção Civil, GNR e bombeiros. EM EMERGÊNCIA: 112.",
        "Distância à estrada é uma aproximação (vértice mais próximo da "
        "linha, não a distância perpendicular exata).",
        "A faixa de gestão de combustível aqui indicada é derivada "
        "automaticamente da classificação de solo do PDM -- confirma sempre "
        "no PMDFCI (Plano Municipal de Defesa da Floresta Contra Incêndios) "
        "da Câmara Municipal de Silves antes de agir.",
    ]

    try:
        risco = _query_ponto(LAYER_RISCO_INCENDIO, lat, lon)
        historico = _query_ponto(LAYER_INCENDIOS_HISTORICO, lat, lon)
        solo = _query_ponto(LAYER_SOLO, lat, lon)
        dist_estrada = _distancia_estrada_mais_proxima(lat, lon)
    except Exception as e:
        return {
            "engine": "Ambiental",
            "question": "Que riscos ambientais existem, e qual a obrigação de limpeza de combustível?",
            "answer": None,
            "knowledge_level": "FACT",
            "confidence": {"label": "Baixa", "reason": str(e)},
            "limitations": [str(e)],
            "sources": ["sigeo.cm-silves.pt (PDM_MS)"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    classe_risco = None
    if risco:
        attrs = risco[0]["attributes"]
        classe_risco = attrs.get("DESIGNACAO_PO") or attrs.get("SUBTEMA_PO") or "Classificado (ver evidência)"

    ja_ardeu = len(historico) > 0

    # Faixa legal de gestao de combustivel (DL 82/2021, alterado pelo DL 6/2025),
    # derivada da classificacao de solo ja usada pelo Motor Juridico.
    faixa_m = None
    motivo_faixa = "Classificação de solo não determinada -- consulta o PMDFCI do município."
    if solo:
        attrs = solo[0]["attributes"]
        subtema = attrs.get("SUBTEMA_PO") or ""
        designacao = attrs.get("DESIGNACAO_PO") or ""
        if "Florestal" in designacao or "Natural" in designacao:
            faixa_m = 50
            motivo_faixa = f"Solo classificado como '{designacao}' -- território florestal: faixa de 50m à volta de edificações."
        elif "Agrícola" in designacao:
            faixa_m = 10
            motivo_faixa = f"Solo classificado como '{designacao}' -- território agrícola: faixa de 10m à volta de edificações."
        elif subtema == "Solo Urbano":
            motivo_faixa = f"Solo urbano ('{designacao}') -- a faixa de 50/10m aplica-se a espaços rurais; para solo urbano consulta o regulamento municipal específico."
        else:
            motivo_faixa = f"Classificação '{designacao}' não mapeada automaticamente para uma faixa -- consulta o PMDFCI."

    zona_protecao = {"centro": [lat, lon], "raio_m": faixa_m} if faixa_m else None

    confianca = "Alta" if (risco and solo) else "Média"

    return {
        "engine": "Ambiental",
        "question": "Que riscos ambientais existem, e qual a obrigação de limpeza de combustível?",
        "answer": {
            "classe_risco_incendio": classe_risco,
            "ja_ardeu_antes": ja_ardeu,
            "faixa_gestao_combustivel_m": faixa_m,
            "motivo_faixa": motivo_faixa,
            "distancia_estrada_mais_proxima_m": round(dist_estrada, 0) if dist_estrada else None,
            "zona_protecao": zona_protecao,
        },
        "knowledge_level": "FACT",
        "confidence": {
            "label": confianca,
            "reason": "Classificação de risco e de solo vêm diretamente do PDM oficial de Silves.",
        },
        "limitations": limitations,
        "sources": [
            "sigeo.cm-silves.pt/arcgis/rest/services/PDM_MS/MapServer",
            "Decreto-Lei n.º 82/2021 (alterado pelo Decreto-Lei n.º 6/2025) -- Sistema de Gestão Integrada de Fogos Rurais",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
