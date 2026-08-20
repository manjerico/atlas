"""
Atlas - Motor Energetico (Solar) v1

Combina duas fontes oficiais europeias:
  1. PVGIS (Comissao Europeia / JRC) -- irradiacao e producao fotovoltaica.
  2. Open Topo Data / EU-DEM (Copernicus, resolucao 25m) -- elevacao do
     terreno, usada para calcular declive e orientacao reais do local.

IMPORTANTE -- arquitetura:
O PVGIS proibe explicitamente pedidos AJAX/CORS a partir de um browser
("access to PVGIS APIs via AJAX is not allowed"). Por isso este motor
corre do lado do servidor, nao no browser.

Uso:
    python motor_solar.py <latitude> <longitude> [peakpower_kw]
"""

import sys
import json
import math
from datetime import datetime, timezone
import urllib.request
import urllib.parse

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc"
OPENTOPO_URL = "https://api.opentopodata.org/v1/eudem25m"

OFFSET_M = 50.0  # distancia aos pontos vizinhos usados para estimar o declive


# ---------------------------------------------------------------------
# Elevacao / declive / orientacao (Open Topo Data, EU-DEM Copernicus)
# ---------------------------------------------------------------------
def _deslocar(lat, lon, offset_m):
    delta_lat = offset_m / 111_320.0
    delta_lon = offset_m / (111_320.0 * math.cos(math.radians(lat)))
    return {
        "centro": (lat, lon),
        "norte": (lat + delta_lat, lon),
        "sul": (lat - delta_lat, lon),
        "este": (lat, lon + delta_lon),
        "oeste": (lat, lon - delta_lon),
    }


def obter_elevacoes(lat, lon, offset_m=OFFSET_M):
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
    return elevs


def calcular_declive_orientacao(elevs, offset_m=OFFSET_M):
    dzdx = (elevs["este"] - elevs["oeste"]) / (2 * offset_m)
    dzdy = (elevs["norte"] - elevs["sul"]) / (2 * offset_m)
    declive_deg = math.degrees(math.atan(math.sqrt(dzdx ** 2 + dzdy ** 2)))
    vx, vy = -dzdx, -dzdy
    orientacao_deg = math.degrees(math.atan2(vx, vy)) % 360
    return declive_deg, orientacao_deg


def orientacao_para_label(orientacao_deg):
    labels = ["Norte", "Nordeste", "Este", "Sudeste", "Sul", "Sudoeste", "Oeste", "Noroeste"]
    idx = round(orientacao_deg / 45) % 8
    return labels[idx]


def compass_para_pvgis_aspect(orientacao_deg):
    aspect = orientacao_deg - 180
    if aspect > 180:
        aspect -= 360
    elif aspect <= -180:
        aspect += 360
    return aspect


# ---------------------------------------------------------------------
# PVGIS
# ---------------------------------------------------------------------
def consultar_pvgis(lat, lon, peakpower=1.0, loss=14.0, angle=None, aspect=None, optimalangles=False):
    params = {
        "lat": lat, "lon": lon, "peakpower": peakpower, "loss": loss,
        "outputformat": "json",
    }
    if optimalangles:
        params["optimalangles"] = 1
    else:
        params["angle"] = angle
        params["aspect"] = aspect

    url = f"{PVGIS_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "AtlasPrototype/0.1 (projeto pessoal, uso nao-comercial)"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def classificar_potencial(especifico_kwh_kwp):
    if especifico_kwh_kwp >= 1700:
        return "Muito elevado"
    elif especifico_kwh_kwp >= 1500:
        return "Elevado"
    elif especifico_kwh_kwp >= 1300:
        return "Moderado"
    return "Baixo"


# ---------------------------------------------------------------------
# Conclusao
# ---------------------------------------------------------------------
def montar_conclusao(lat, lon, peakpower=1.0):
    evidencia = []
    limitacoes = [
        "O calculo de sombreamento do PVGIS usa um modelo de elevacao do "
        "terreno com resolucao de cerca de 90 metros; nao capta obstrucoes "
        "proximas como arvores ou edificios vizinhos.",
        "E uma media historica de longo prazo, nao uma previsao para um ano especifico.",
        "Nao inclui custo de instalacao, tarifa de venda a rede, nem retorno "
        "de investimento -- e um dado tecnico (Nivel 2), nao uma projecao "
        "economica (Nivel 3).",
    ]

    try:
        data_otimo = consultar_pvgis(lat, lon, peakpower=peakpower, optimalangles=True)
        totals = data_otimo["outputs"]["totals"]["fixed"]
        mounting = data_otimo["inputs"]["mounting_system"]["fixed"]
        e_y_otimo = totals["E_y"]
        h_y_otimo = totals["H(i)_y"]
        angulo_otimo = mounting["slope"]["value"]
        orientacao_otima = mounting["azimuth"]["value"]
        evidencia.append({"fonte": "PVGIS PVcalc (optimalangles=1)", "E_y": e_y_otimo, "H(i)_y": h_y_otimo})
    except Exception as e:
        return _erro(lat, lon, f"Erro ao consultar o PVGIS (melhor caso): {e}")

    terreno_real = None
    try:
        elevs = obter_elevacoes(lat, lon)
        declive_deg, orientacao_deg = calcular_declive_orientacao(elevs)
        evidencia.append({"fonte": "Open Topo Data / EU-DEM Copernicus (25m)", "elevacoes_m": elevs})

        if declive_deg < 3:
            terreno_real = {
                "declive_estimado_graus": round(declive_deg, 1),
                "orientacao_estimada": "Terreno praticamente plano -- orientacao pouco relevante",
                "producao_estimada_kwh_por_kwp_ano": round(e_y_otimo, 1),
                "percentagem_do_potencial_otimo": 100.0,
            }
        else:
            pvgis_aspect = compass_para_pvgis_aspect(orientacao_deg)
            angulo_pvgis = min(declive_deg, 90.0)
            data_terreno = consultar_pvgis(
                lat, lon, peakpower=peakpower,
                angle=angulo_pvgis, aspect=pvgis_aspect, optimalangles=False,
            )
            e_y_terreno = data_terreno["outputs"]["totals"]["fixed"]["E_y"]
            evidencia.append({
                "fonte": "PVGIS PVcalc (angulo/orientacao do terreno)",
                "angle_usado": angulo_pvgis, "aspect_usado": pvgis_aspect, "E_y": e_y_terreno,
            })
            terreno_real = {
                "declive_estimado_graus": round(declive_deg, 1),
                "orientacao_estimada": f"{orientacao_para_label(orientacao_deg)} ({orientacao_deg:.0f} graus)",
                "producao_estimada_kwh_por_kwp_ano": round(e_y_terreno, 1),
                "percentagem_do_potencial_otimo": round(100 * e_y_terreno / e_y_otimo, 1),
            }
        limitacoes.insert(0,
            "Declive e orientacao sao uma APROXIMACAO por diferencas finitas "
            "entre 4 pontos a 50m de distancia, usando um modelo de elevacao "
            "(EU-DEM) de 25m de resolucao -- nao substitui um levantamento "
            "topografico real da parcela."
        )
    except Exception as e:
        limitacoes.insert(0, f"Nao foi possivel calcular declive/orientacao real do terreno: {e}")

    especifico = e_y_otimo / peakpower
    nivel = classificar_potencial(especifico)

    return {
        "engine": "Energetico",
        "question": "Existe potencial para producao fotovoltaica?",
        "coordinates": {"lat": lat, "lon": lon},
        "answer": {
            "melhor_caso": {
                "potencial": nivel,
                "producao_especifica_kwh_por_kwp_ano": round(especifico, 1),
                "angulo_otimo_graus": angulo_otimo,
                "orientacao_otima_graus": orientacao_otima,
                "irradiacao_anual_kwh_m2": round(h_y_otimo, 1),
            },
            "terreno_real": terreno_real,
        },
        "knowledge_level": "INFERENCE",
        "confidence": {
            "label": "Alta (melhor caso) / Media (terreno real)",
            "reason": (
                "O 'melhor caso' vem diretamente do PVGIS, validado cientificamente. "
                "O 'terreno real' e uma aproximacao geometrica sobre um DEM de 25m -- "
                "util como indicacao, nao como projeto de engenharia."
            ),
        },
        "evidence": evidencia,
        "limitations": limitacoes,
        "sources": [
            "https://re.jrc.ec.europa.eu (PVGIS, Comissao Europeia / JRC)",
            "https://www.opentopodata.org (EU-DEM, Copernicus)",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _erro(lat, lon, motivo):
    return {
        "engine": "Energetico",
        "question": "Existe potencial para producao fotovoltaica?",
        "coordinates": {"lat": lat, "lon": lon},
        "answer": None,
        "knowledge_level": "INFERENCE",
        "confidence": {"label": "Baixa", "reason": motivo},
        "evidence": [],
        "limitations": [motivo],
        "sources": ["https://re.jrc.ec.europa.eu (PVGIS, Comissao Europeia / JRC)"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print("Uso: python motor_solar.py <latitude> <longitude> [peakpower_kw]")
        sys.exit(1)
    lat, lon = float(sys.argv[1]), float(sys.argv[2])
    peakpower = float(sys.argv[3]) if len(sys.argv) == 4 else 1.0
    print(json.dumps(montar_conclusao(lat, lon, peakpower=peakpower), indent=2, ensure_ascii=False))
