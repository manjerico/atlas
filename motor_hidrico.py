"""
Atlas - Motor Hidrico v1

Combina tres fontes:
  1. SIG do PDM de Silves -- presenca de linhas de agua (Dominio Publico
     Hidrico), captacoes de agua subterranea, albufeiras e aproveitamentos
     hidroagricolas (rega) num raio de 1km do ponto.
  2. Open-Meteo (ERA5-Land, ECMWF) -- precipitacao media anual dos ultimos
     10 anos, como contexto climatico regional.
  3. LNEG (Recursos Hidrogeologicos) -- sistema aquifero, pontos de agua
     (furos/pocos/nascentes) inventariados, e um contexto regional agregado
     (nao uma previsao pontual) de como a agua subterranea tem sido usada
     numa zona alargada.

O que este motor responde: "ha indicadores de agua disponivel perto deste
local?" -- NAO responde "tenho caudal suficiente" nem "onde devo furar" --
isso exige um estudo hidrogeologico real no terreno.
"""

import sys
import json
import math
from datetime import datetime, timezone, date
import urllib.request
import urllib.parse

BASE_URL = "https://sigeo.cm-silves.pt/arcgis/rest/services/PDM_MS/MapServer"
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
LNEG_URL = "https://sig.lneg.pt/server/rest/services/RecursosHidro/MapServer"
LNEG_PONTOS_AGUA_LAYER_ID = 0
LNEG_AQUIFEROS_LAYER_ID = 2

RAIO_BUSCA_M = 1000  # metros

TIPO_PONTO_AGUA = {1: "Furo", 2: "Poço", 3: "Nascente", 4: "Sondagem"}

USO_PONTO_AGUA = {
    1: "Abastecimento doméstico", 2: "Abastecimento público", 3: "Agricultura",
    4: "Agropecuária", 5: "Aquacultura", 6: "Ecológico", 7: "Engarrafamento",
    8: "Entulhado", 9: "Geotermia", 10: "Instituição", 11: "Misto",
    12: "Outras indústrias", 13: "Outro uso", 14: "Pecuária", 15: "Recreio",
    16: "Termalismo", 17: "Geotecnia",
}
USOS_AGRICOLAS = {"Agricultura", "Agropecuária", "Pecuária", "Aquacultura"}

CAMADAS_HIDRICAS = {
    391: {"nome": "Domínio Público Hídrico (Águas Fluviais) - linha", "categoria": "agua_superficie"},
    392: {"nome": "Domínio Público Hídrico (Águas Fluviais) - polígono", "categoria": "agua_superficie"},
    394: {"nome": "Albufeiras / Lagos de Águas Públicas", "categoria": "agua_superficie"},
    395: {"nome": "Captação de Águas Subterrâneas para Abastecimento Público", "categoria": "agua_subterranea"},
    396: {"nome": "Captações de Águas Subterrâneas (polígono)", "categoria": "agua_subterranea"},
    403: {"nome": "Obras de Aproveitamento Hidroagrícola - linha", "categoria": "rega"},
    404: {"nome": "Obras de Aproveitamento Hidroagrícola - polígono", "categoria": "rega"},
}


def _query_layer_buffer(layer_id, lat, lon, raio_m=RAIO_BUSCA_M):
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


def obter_precipitacao_media_anual(lat, lon, anos=10):
    ano_atual = date.today().year
    ano_fim = ano_atual - 1
    ano_inicio = ano_fim - anos + 1

    params = {
        "latitude": lat, "longitude": lon,
        "start_date": f"{ano_inicio}-01-01", "end_date": f"{ano_fim}-12-31",
        "daily": "precipitation_sum", "timezone": "auto",
    }
    url = f"{OPEN_METEO_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "AtlasPrototype/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    valores = [v for v in data["daily"]["precipitation_sum"] if v is not None]
    total_periodo = sum(valores)
    media_anual = total_periodo / anos
    return round(media_anual, 1), ano_inicio, ano_fim


def classificar_precipitacao(mm_ano):
    if mm_ano < 400:
        return "Baixa (clima semi-árido)"
    elif mm_ano < 700:
        return "Moderada (típica do sul de Portugal)"
    elif mm_ano < 1000:
        return "Elevada"
    return "Muito elevada"


def obter_sistema_aquifero(lat, lon):
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "NomeCompleto,SistemaAquifero,Idade,CodigoInag",
        "where": "1=1",
        "returnGeometry": "false",
        "f": "json",
    }
    url = f"{LNEG_URL}/{LNEG_AQUIFEROS_LAYER_ID}/query?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "AtlasPrototype/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    features = data.get("features", [])
    if not features:
        return None
    return features[0]["attributes"]


def obter_pontos_agua_perto(lat, lon, raio_m=RAIO_BUSCA_M):
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": raio_m,
        "units": "esriSRUnit_Meter",
        "outFields": "IDTipoPA,IDUso,Local",
        "where": "1=1",
        "returnGeometry": "false",
        "f": "json",
    }
    url = f"{LNEG_URL}/{LNEG_PONTOS_AGUA_LAYER_ID}/query?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "AtlasPrototype/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [f["attributes"] for f in data.get("features", [])]


def obter_contexto_regional_agua(lat, lon, raio_m=5000):
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": raio_m,
        "units": "esriSRUnit_Meter",
        "outFields": "IDTipoPA,IDUso",
        "where": "1=1",
        "returnGeometry": "false",
        "f": "json",
    }
    url = f"{LNEG_URL}/{LNEG_PONTOS_AGUA_LAYER_ID}/query?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "AtlasPrototype/0.1"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    pontos = [f["attributes"] for f in data.get("features", [])]

    distribuicao_uso = {}
    distribuicao_tipo = {}
    n_agricola = 0
    for p in pontos:
        uso = USO_PONTO_AGUA.get(p.get("IDUso"), "Não especificado")
        tipo = TIPO_PONTO_AGUA.get(p.get("IDTipoPA"), "Desconhecido")
        distribuicao_uso[uso] = distribuicao_uso.get(uso, 0) + 1
        distribuicao_tipo[tipo] = distribuicao_tipo.get(tipo, 0) + 1
        if uso in USOS_AGRICOLAS:
            n_agricola += 1

    total = len(pontos)
    area_km2 = math.pi * (raio_m / 1000) ** 2

    return {
        "raio_km": round(raio_m / 1000, 1),
        "area_km2": round(area_km2, 1),
        "total_pontos_inventariados": total,
        "densidade_pontos_por_km2": round(total / area_km2, 2) if area_km2 else None,
        "percentagem_uso_agricola": round(100 * n_agricola / total, 1) if total else None,
        "distribuicao_uso": dict(sorted(distribuicao_uso.items(), key=lambda kv: -kv[1])),
        "distribuicao_tipo": distribuicao_tipo,
    }


def montar_conclusao(lat, lon):
    resultados = {}
    erro_sig = None
    for layer_id in CAMADAS_HIDRICAS:
        try:
            resultados[layer_id] = _query_layer_buffer(layer_id, lat, lon)
        except Exception as e:
            resultados[layer_id] = []
            erro_sig = str(e)

    def presente(categoria):
        return any(
            isinstance(resultados.get(lid), list) and resultados[lid]
            for lid, meta in CAMADAS_HIDRICAS.items() if meta["categoria"] == categoria
        )

    indicadores = {
        "agua_superficie_perto": presente("agua_superficie"),
        "captacao_subterranea_perto": presente("agua_subterranea"),
        "infraestrutura_rega_perto": presente("rega"),
    }

    precipitacao_media = None
    periodo = None
    try:
        precipitacao_media, ano_i, ano_f = obter_precipitacao_media_anual(lat, lon)
        periodo = f"{ano_i}-{ano_f}"
    except Exception as e:
        erro_precip = str(e)
    else:
        erro_precip = None

    aquifero = None
    pontos_agua = []
    contexto_regional = None
    erro_lneg = None
    try:
        aquifero = obter_sistema_aquifero(lat, lon)
        pontos_agua = obter_pontos_agua_perto(lat, lon)
        contexto_regional = obter_contexto_regional_agua(lat, lon)
    except Exception as e:
        erro_lneg = str(e)

    contagem_tipos = {}
    for p in pontos_agua:
        tipo = TIPO_PONTO_AGUA.get(p.get("IDTipoPA"), "Desconhecido")
        contagem_tipos[tipo] = contagem_tipos.get(tipo, 0) + 1

    limitations = [
        f"Procura limitada a um raio de {RAIO_BUSCA_M}m -- nao indica caudal, "
        "qualidade da agua, nem direitos de uso/exploracao.",
        "Nao substitui um estudo hidrogeologico ou projeto de rega para "
        "decisoes de investimento -- e um indicador de triagem, nao uma "
        "garantia de disponibilidade de agua.",
        "A precipitacao e uma media histórica regional (ERA5-Land, ~9km de "
        "resolucao) -- nao reflete variacoes locais nem anos excecionais "
        "(secas ou cheias).",
        "A Base de Dados de Recursos Hidrogeologicos do LNEG nao inclui "
        "profundidade do nivel freatico nem caudal -- so confirma a "
        "existencia e o tipo de pontos de agua inventariados, e o sistema "
        "aquifero geologico. Um furo produtivo aqui nao garante que um novo "
        "furo tera o mesmo resultado -- isso depende de teste no terreno.",
        "O 'contexto regional' e uma estatistica agregada de uma zona larga "
        "(varios km a volta, nao esta parcela) -- serve para uma primeira "
        "triagem (ex: esta zona tem sido mais usada para agricultura ou para "
        "abastecimento domestico), nao prevê se ESTE terreno em particular "
        "tem agua disponivel. So um estudo local esclarece isso.",
    ]
    if erro_sig:
        limitations.insert(0, f"Algumas camadas do SIG de Silves falharam: {erro_sig}")
    if erro_precip:
        limitations.insert(0, f"Nao foi possivel obter precipitacao: {erro_precip}")
    if erro_lneg:
        limitations.insert(0, f"Nao foi possivel consultar o LNEG (recursos hidrogeologicos): {erro_lneg}")

    n_indicadores = sum(indicadores.values())
    if erro_sig or erro_precip:
        confianca = "Baixa"
    elif n_indicadores >= 2:
        confianca = "Média"
    else:
        confianca = "Média"

    return {
        "engine": "Hidrico",
        "question": "Tenho disponibilidade de água suficiente?",
        "coordinates": {"lat": lat, "lon": lon},
        "answer": {
            "indicadores_num_raio_1km": indicadores,
            "precipitacao_media_mm_ano": precipitacao_media,
            "precipitacao_classificacao": classificar_precipitacao(precipitacao_media) if precipitacao_media else None,
            "periodo_referencia_precipitacao": periodo,
            "sistema_aquifero": {
                "nome": aquifero.get("NomeCompleto") if aquifero else None,
                "idade_geologica": aquifero.get("Idade") if aquifero else None,
            } if aquifero else None,
            "pontos_agua_subterranea": {
                "total_no_raio": len(pontos_agua),
                "por_tipo": contagem_tipos,
            },
            "contexto_regional_agua_subterranea": contexto_regional,
        },
        "knowledge_level": "INFERENCE",
        "confidence": {
            "label": confianca,
            "reason": (
                "Presenca/ausencia de agua de superficie ou infraestrutura num raio "
                "de 1km e um indicador indireto -- nunca corresponde a uma medicao "
                "direta de disponibilidade de agua na parcela."
            ),
        },
        "evidence": [
            {"layer_id": lid, "nome": meta["nome"], "features_no_raio": len(resultados.get(lid, []))}
            for lid, meta in CAMADAS_HIDRICAS.items()
        ] + (
            [{"fonte": "Open-Meteo (ERA5-Land)", "precipitacao_media_mm_ano": precipitacao_media, "periodo": periodo}]
            if precipitacao_media else []
        ) + (
            [{"fonte": "LNEG (Sistemas Aquíferos)", "sistema": aquifero.get("NomeCompleto")}]
            if aquifero else []
        ) + [{"fonte": "LNEG (Pontos de Água)", "total_no_raio": len(pontos_agua), "por_tipo": contagem_tipos}],
        "limitations": limitations,
        "sources": [
            "sigeo.cm-silves.pt/arcgis/rest/services/PDM_MS/MapServer",
            "https://open-meteo.com (ERA5-Land, ECMWF)",
            "https://sig.lneg.pt (LNEG -- Recursos Hidrogeológicos)",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python motor_hidrico.py <latitude> <longitude>")
        sys.exit(1)
    lat, lon = float(sys.argv[1]), float(sys.argv[2])
    print(json.dumps(montar_conclusao(lat, lon), indent=2, ensure_ascii=False))
