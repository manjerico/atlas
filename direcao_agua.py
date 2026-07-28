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


def _extremos(geometry, bbox=None):
    """Devolve (primeiro_ponto, ultimo_ponto), cada um [lon, lat], de uma
    LineString/MultiLineString GeoJSON.

    Para MultiLineString (varias partes desconectadas debaixo do mesmo
    registo -- comum em hidrografia, ex: um rio inteiro com troços em
    varios sitios do concelho), escolhe-se a parte que realmente tem um
    ponto dentro do bbox pedido, nao apenas a primeira parte da lista --
    caso contrario arriscamo-nos a apanhar um troço bem longe da area
    que o utilizador está a ver."""
    if geometry["type"] == "LineString":
        partes = [geometry["coordinates"]]
    elif geometry["type"] == "MultiLineString":
        partes = geometry["coordinates"]
    else:
        return None

    partes = [p for p in partes if len(p) >= 2]
    if not partes:
        return None

    coords = partes[0]
    if bbox is not None and len(partes) > 1:
        xmin, ymin, xmax, ymax = bbox
        for p in partes:
            if any(xmin <= pt[0] <= xmax and ymin <= pt[1] <= ymax for pt in p):
                coords = p
                break

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
        extremos = _extremos(f["geometry"], bbox=(xmin, ymin, xmax, ymax))
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
