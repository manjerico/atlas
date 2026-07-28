"""
Atlas - Sentido da corrente de agua

A ordem em que os vertices de uma linha de agua foram desenhados no SIG
NAO garante o sentido real do escoamento (e um erro comum assumir isso).
Para saber o sentido real, comparamos a elevacao das duas pontas da linha
(via EU-DEM/Open Topo Data, cobertura nacional) -- a agua vai sempre da
cota mais alta para a mais baixa.
"""

import json
import urllib.request
import urllib.parse

PDM_URL = "https://sigeo.cm-silves.pt/arcgis/rest/services/PDM_MS/MapServer"
LINHA_AGUA_LAYER_ID = 391  # Dominio Publico Hidrico (Aguas Fluviais) -- linha
OPENTOPO_URL = "https://api.opentopodata.org/v1/eudem25m"


def _query_linhas(xmin, ymin, xmax, ymax):
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
    url = f"{PDM_URL}/{LINHA_AGUA_LAYER_ID}/query?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "AtlasPrototype/0.1"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extremos(geometry):
    """Devolve (primeiro_ponto, ultimo_ponto), cada um [lon, lat], de uma
    LineString/MultiLineString GeoJSON. Simplificacao: para MultiLineString
    usa-se so a primeira parte."""
    if geometry["type"] == "LineString":
        coords = geometry["coordinates"]
    elif geometry["type"] == "MultiLineString":
        if not geometry["coordinates"]:
            return None
        coords = geometry["coordinates"][0]
    else:
        return None
    if len(coords) < 2:
        return None
    return coords[0], coords[-1]


def _elevacoes_lote(pontos_lonlat, tamanho_lote=90):
    """Consulta a Open Topo Data em lotes (o servico publico aceita cerca
    de 100 pontos por pedido)."""
    elevacoes = []
    for i in range(0, len(pontos_lonlat), tamanho_lote):
        lote = pontos_lonlat[i:i + tamanho_lote]
        locations = "|".join(f"{lat},{lon}" for lon, lat in lote)
        url = f"{OPENTOPO_URL}?{urllib.parse.urlencode({'locations': locations})}"
        req = urllib.request.Request(url, headers={"User-Agent": "AtlasPrototype/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elevacoes.extend(r["elevation"] for r in data["results"])
    return elevacoes


def calcular_direcoes(xmin, ymin, xmax, ymax, max_linhas=60):
    geo = _query_linhas(xmin, ymin, xmax, ymax)
    todas_features = geo.get("features", [])
    features = todas_features[:max_linhas]

    linhas_validas = []
    pontos_para_elevacao = []
    for f in features:
        extremos = _extremos(f["geometry"])
        if extremos is None:
            continue
        linhas_validas.append(extremos)
        pontos_para_elevacao.append(extremos[0])
        pontos_para_elevacao.append(extremos[1])

    if not pontos_para_elevacao:
        return {"linhas": [], "aviso": "Nenhuma linha de água encontrada nesta vista."}

    elevacoes = _elevacoes_lote(pontos_para_elevacao)

    resultado = []
    for i, (p1, p2) in enumerate(linhas_validas):
        e1 = elevacoes[2 * i]
        e2 = elevacoes[2 * i + 1]
        if e1 is None or e2 is None:
            continue
        if e1 >= e2:
            origem, destino = p1, p2
        else:
            origem, destino = p2, p1
        resultado.append({
            "origem": [origem[1], origem[0]],    # [lat, lon]
            "destino": [destino[1], destino[0]],  # [lat, lon]
            "desnivel_m": round(abs(e1 - e2), 1),
        })

    aviso = None
    if len(todas_features) > max_linhas:
        aviso = f"Mostradas apenas as primeiras {max_linhas} linhas nesta vista (havia mais -- aproxima o zoom)."

    return {"linhas": resultado, "aviso": aviso}
