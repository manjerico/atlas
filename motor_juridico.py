"""
Atlas - Motor Juridico (Silves)
Modulo reutilizavel -- ver atlas_motor_juridico_silves.py para a versao
original em linha de comandos. A logica e identica.
"""

import json
from datetime import datetime, timezone
import urllib.request
import urllib.parse

BASE_URL = "https://sigeo.cm-silves.pt/arcgis/rest/services/PDM_MS/MapServer"
CADASTRO_URL = "https://sigeo.cm-silves.pt/arcgis/rest/services/CadastroDGTwfs/MapServer"
CADASTRO_PREDIO_LAYER_ID = 2

LAYERS = {
    465: {"nome": "Classificacao e Qualificacao do Solo", "categoria": "ordenamento"},
    406: {"nome": "Reserva Agricola Nacional (RAN)", "categoria": "condicionante"},
    399: {"nome": "Reserva Ecologica Nacional (REN)", "categoria": "condicionante"},
    400: {"nome": "Rede Natura 2000", "categoria": "condicionante"},
    461: {"nome": "Cheias tecnicas", "categoria": "risco"},
    462: {"nome": "Suscetibilidade a Fenomenos Perigosos", "categoria": "risco"},
    460: {"nome": "Areas Criticas de Instabilidade de Vertentes", "categoria": "risco"},
    571: {"nome": "Faixa de Protecao ao Litoral", "categoria": "condicionante"},
    452: {"nome": "Faixa Costeira do Litoral Sul", "categoria": "condicionante"},
    409: {"nome": "Classe de Risco de Incendio", "categoria": "risco"},
}


def _query_layer(base_url, layer_id, lat, lon):
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
    url = f"{base_url}/{layer_id}/query?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "AtlasPrototype/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    features = data.get("features", [])
    return [f for f in features if f.get("attributes", {}).get("DESACTIVO") not in (1, "1")]


def montar_conclusao(lat, lon):
    resultados = {}
    for layer_id in LAYERS:
        try:
            resultados[layer_id] = _query_layer(BASE_URL, layer_id, lat, lon)
        except Exception as e:
            resultados[layer_id] = f"ERRO: {e}"

    try:
        predio = _query_layer(CADASTRO_URL, CADASTRO_PREDIO_LAYER_ID, lat, lon)
    except Exception:
        predio = []

    solo_features = resultados.get(465, [])
    if isinstance(solo_features, list) and solo_features:
        attrs = solo_features[0]["attributes"]
        classificacao = f'{attrs.get("SUBTEMA_PO")} - {attrs.get("DESIGNACAO_PO")}'
        area_m2 = attrs.get("SHAPE.STArea()")
    else:
        classificacao = "Nao determinado (sem resposta da camada de solo)"
        area_m2 = None

    condicionantes_ativas = [
        meta["nome"] for lid, meta in LAYERS.items()
        if meta["categoria"] == "condicionante"
        and isinstance(resultados.get(lid), list) and resultados[lid]
    ]
    riscos_ativos = [
        meta["nome"] for lid, meta in LAYERS.items()
        if meta["categoria"] == "risco"
        and isinstance(resultados.get(lid), list) and resultados[lid]
    ]

    if area_m2 is None:
        confianca, motivo_confianca = "Baixa", "Nao foi possivel obter a classificacao de solo."
    elif area_m2 > 10_000_000:
        confianca = "Media"
        motivo_confianca = (
            f"Classificacao obtida, mas o poligono cobre {area_m2/1_000_000:.1f} km2 "
            f"-- possivel categoria generica, nao especifica desta parcela."
        )
    else:
        confianca, motivo_confianca = "Alta", "Classificacao obtida de poligono de escala compativel com parcela."

    identidade_parcela = None
    if isinstance(predio, list) and predio:
        a = predio[0]["attributes"]
        identidade_parcela = {
            "freguesia": a.get("FREG"),
            "seccao": a.get("seccao"),
            "predio_no": a.get("nprd"),
            "area_ha": round(a["Shape.STArea()"] / 10000, 2) if a.get("Shape.STArea()") else None,
        }

    return {
        "engine": "Juridico",
        "question": "Posso construir neste local?",
        "coordinates": {"lat": lat, "lon": lon},
        "identidade_parcela": identidade_parcela,
        "answer": {
            "classificacao_solo": classificacao,
            "condicionantes_ativas": condicionantes_ativas or ["Nenhuma identificada"],
            "riscos_identificados": riscos_ativos or ["Nenhum identificado"],
        },
        "knowledge_level": "FACT",
        "confidence": {"label": confianca, "reason": motivo_confianca},
        "evidence": [
            {
                "layer_id": lid,
                "nome": meta["nome"],
                "features_encontradas": len(resultados[lid]) if isinstance(resultados[lid], list) else resultados[lid],
            }
            for lid, meta in LAYERS.items()
        ],
        "limitations": [
            "Baseado apenas nas camadas do servico PDM_MS de Silves; nao substitui consulta oficial ao PDM publicado em Diario da Republica.",
            "Nao considera declive, coberto vegetal real, acessos, nem condicionantes fora das camadas listadas.",
            "Resultado pontual -- nao reflete variacoes de classificacao dentro de uma parcela maior.",
        ],
        "sources": ["sigeo.cm-silves.pt/arcgis/rest/services/PDM_MS/MapServer"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
