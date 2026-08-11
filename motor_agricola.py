"""
Atlas - Motor Agronomico v0

Combina:
  1. EU-DEM / Open Topo Data -- declive do terreno.
  2. SoilGrids (ISRIC, Holanda) -- textura do solo (argila/areia/limo) e pH,
     a 250m de resolucao, modelado globalmente por machine learning sobre
     perfis de solo reais (WoSIS) e variaveis ambientais.

O que este motor NAO faz: nao recomenda uma cultura especifica, nao estima
rendimento, nao diz "compensa financeiramente". Fica no Nivel 2.
"""

import sys
import json
import math
import time
from datetime import datetime, timezone
import urllib.request
import urllib.parse

SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
OPENTOPO_URL = "https://api.opentopodata.org/v1/eudem25m"
OFFSET_M = 50.0


def _deslocar(lat, lon, offset_m):
    delta_lat = offset_m / 111_320.0
    delta_lon = offset_m / (111_320.0 * math.cos(math.radians(lat)))
    return {
        "centro": (lat, lon), "norte": (lat + delta_lat, lon), "sul": (lat - delta_lat, lon),
        "este": (lat, lon + delta_lon), "oeste": (lat, lon - delta_lon),
    }


def obter_declive(lat, lon, offset_m=OFFSET_M):
    pontos = _deslocar(lat, lon, offset_m)
    ordem = ["centro", "norte", "sul", "este", "oeste"]
    locations = "|".join(f"{pontos[k][0]},{pontos[k][1]}" for k in ordem)
    url = f"{OPENTOPO_URL}?{urllib.parse.urlencode({'locations': locations})}"
    req = urllib.request.Request(url, headers={"User-Agent": "AtlasPrototype/0.1"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("status") != "OK":
        raise RuntimeError(f"Open Topo Data devolveu estado: {data.get('status')}")
    elevs = {k: r["elevation"] for k, r in zip(ordem, data["results"])}
    dzdx = (elevs["este"] - elevs["oeste"]) / (2 * offset_m)
    dzdy = (elevs["norte"] - elevs["sul"]) / (2 * offset_m)
    declive_deg = math.degrees(math.atan(math.sqrt(dzdx ** 2 + dzdy ** 2)))
    return declive_deg


def consultar_soilgrids(lat, lon, depth="0-5cm", tentativas=2, timeout=35):
    params = [
        ("lon", lon), ("lat", lat),
        ("property", "clay"), ("property", "sand"), ("property", "silt"),
        ("property", "phh2o"), ("property", "soc"),
        ("depth", depth), ("value", "mean"),
    ]
    url = f"{SOILGRIDS_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "AtlasPrototype/0.1"})

    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            ultimo_erro = e
            if tentativa < tentativas:
                time.sleep(2)
    raise ultimo_erro


def extrair_propriedades(data):
    props = {}
    for layer in data["properties"]["layers"]:
        nome = layer["name"]
        fator = layer["unit_measure"]["d_factor"]
        valor_bruto = layer["depths"][0]["values"]["mean"]
        props[nome] = None if valor_bruto is None else valor_bruto / fator
    return props


def classificar_textura(clay, sand, silt):
    if clay >= 40:
        if silt >= 40:
            return "Argila siltosa"
        elif sand > 45:
            return "Argila arenosa"
        return "Argila"
    if clay >= 27:
        if sand <= 20:
            return "Franco-argilo-siltoso"
        elif sand > 45:
            return "Franco-argilo-arenoso"
        return "Franco-argiloso"
    if clay >= 7:
        if silt >= 50:
            return "Franco-siltoso" if silt < 80 else "Silte"
        if sand <= 52:
            return "Franco"
        return "Franco-arenoso"
    if silt >= 80:
        return "Silte"
    if sand >= 85 and (silt + 1.5 * clay) < 15:
        return "Areia"
    if sand >= 70 and (silt + 2 * clay) < 30:
        return "Areia-franca"
    return "Franco-arenoso"


def classificar_ph(ph):
    if ph < 5.5:
        return "Acido"
    if ph < 6.5:
        return "Ligeiramente acido"
    if ph < 7.5:
        return "Neutro"
    if ph < 8.5:
        return "Ligeiramente alcalino"
    return "Alcalino"


def montar_conclusao(lat, lon):
    limitations = [
        "SoilGrids e um modelo GLOBAL a 250m de resolucao, calibrado por "
        "machine learning sobre perfis de solo reais e variaveis ambientais "
        "-- nao substitui uma analise de solo feita no terreno.",
        "A classificacao textural usada aqui e uma reconstrucao simplificada "
        "do triangulo USDA, nao o software oficial -- pode divergir perto "
        "das fronteiras entre classes.",
        "Este motor NAO recomenda uma cultura especifica nem estima "
        "rendimento ou retorno de investimento.",
    ]

    try:
        declive_deg = obter_declive(lat, lon)
    except Exception as e:
        declive_deg = None
        limitations.insert(0, f"Nao foi possivel calcular o declive: {e}")

    try:
        dados_solo = consultar_soilgrids(lat, lon)
        props = extrair_propriedades(dados_solo)
    except Exception as e:
        return {
            "engine": "Agronomico",
            "question": "Que utilizacoes agricolas sao mais adequadas?",
            "coordinates": {"lat": lat, "lon": lon},
            "answer": None,
            "knowledge_level": "INFERENCE",
            "confidence": {"label": "Baixa", "reason": f"Erro ao consultar o SoilGrids: {e}"},
            "evidence": [],
            "limitations": [f"Nao foi possivel obter dados de solo: {e}"],
            "sources": ["https://www.isric.org (SoilGrids)"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    clay, sand, silt = props.get("clay"), props.get("sand"), props.get("silt")
    ph = props.get("phh2o")
    soc = props.get("soc")

    textura = classificar_textura(clay, sand, silt) if all(v is not None for v in (clay, sand, silt)) else None
    ph_label = classificar_ph(ph) if ph is not None else None

    return {
        "engine": "Agronomico",
        "question": "Que utilizacoes agricolas sao mais adequadas?",
        "coordinates": {"lat": lat, "lon": lon},
        "answer": {
            "textura_solo": textura,
            "composicao": {"argila_pct": clay, "areia_pct": sand, "limo_pct": silt},
            "ph": {"valor": ph, "classificacao": ph_label},
            "carbono_organico_g_kg": soc,
            "declive_graus": round(declive_deg, 1) if declive_deg is not None else None,
        },
        "knowledge_level": "INFERENCE",
        "confidence": {
            "label": "Media",
            "reason": (
                "Baseado em modelos globais (SoilGrids/EU-DEM) a 250m/25m de "
                "resolucao -- uteis como triagem inicial, nao como substituto "
                "de uma analise de solo real feita no terreno."
            ),
        },
        "evidence": [
            {"fonte": "SoilGrids (ISRIC)", "propriedade": "clay", "valor_pct": clay},
            {"fonte": "SoilGrids (ISRIC)", "propriedade": "sand", "valor_pct": sand},
            {"fonte": "SoilGrids (ISRIC)", "propriedade": "silt", "valor_pct": silt},
            {"fonte": "SoilGrids (ISRIC)", "propriedade": "phh2o", "valor": ph},
            {"fonte": "SoilGrids (ISRIC)", "propriedade": "soc", "valor_g_kg": soc},
            {"fonte": "EU-DEM / Open Topo Data", "propriedade": "declive", "valor_graus": declive_deg},
        ],
        "limitations": limitations,
        "sources": [
            "https://www.isric.org (SoilGrids, ISRIC)",
            "https://www.opentopodata.org (EU-DEM, Copernicus)",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python motor_agricola.py <latitude> <longitude>")
        sys.exit(1)
    lat, lon = float(sys.argv[1]), float(sys.argv[2])
    print(json.dumps(montar_conclusao(lat, lon), indent=2, ensure_ascii=False))
