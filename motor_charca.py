"""
Atlas - Motor Charca

Calcula volume de agua represada por uma barreira (em arco, varios pontos)
sobre o MDT LiDAR (2m) de Silves. Inclui as transformacoes de coordenadas
(WGS84 <-> EPSG:3763, formulas de Snyder) usadas tambem pelos outros
motores baseados em LiDAR (terraplanagem, agricultura, vista 3D).

IMPORTANTE: a transformacao latlon_para_en/en_para_latlon aqui usada NAO
inclui o false easting/northing padrao do EPSG:3763 (200000/300000) --
e uma projecao TM06 "crua", num referencial proprio e interno ao Atlas.
Isto foi validado exaustivamente por round-trip (latlon -> EN -> latlon,
erro sub-milimetrico) e usado de forma consistente em todos os calculos
internos (grelha LiDAR, cadastro, vista 3D). Ao pedir imagens a servicos
externos que esperem EPSG:3763 "a serio" (com false easting/northing), essa
diferenca tem de ser tida em conta -- ver nota em exportar_elevacao_3d.
"""

import sys
import os
import io
import base64
import json
import math
import heapq
from collections import deque
from datetime import datetime, timezone
import numpy as np
import tifffile
from PIL import Image

TIF_NORTE_DEFAULT = os.path.join(os.path.dirname(__file__), "data", "MDT-2m-184043-04-2024_v01.tif")
TIF_SUL_DEFAULT = os.path.join(os.path.dirname(__file__), "data", "MDT-2m-184044-04-2024_v01.tif")

# Parametros do elipsoide GRS80 / ETRS89, projecao Transversa de Mercator
# (base do EPSG:3763 -- ver nota acima sobre o false easting/northing)
A = 6378137.0
F = 1 / 298.257222101
E2 = 2 * F - F ** 2
EP2 = E2 / (1 - E2)
K0 = 1.0
LAT0 = math.radians(39.66825833333333)
LON0 = math.radians(-8.133108333333333)


def _meridional_arc(lat):
    return A * (
        (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256) * lat
        - (3 * E2 / 8 + 3 * E2 ** 2 / 32 + 45 * E2 ** 3 / 1024) * math.sin(2 * lat)
        + (15 * E2 ** 2 / 256 + 45 * E2 ** 3 / 1024) * math.sin(4 * lat)
        - (35 * E2 ** 3 / 3072) * math.sin(6 * lat)
    )


def latlon_para_en(lat_deg, lon_deg):
    """WGS84 lat/lon -> (Easting, Northing), formulas de Snyder."""
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    T = math.tan(lat) ** 2
    C = EP2 * math.cos(lat) ** 2
    Aterm = (lon - LON0) * math.cos(lat)
    Nrad = A / math.sqrt(1 - E2 * math.sin(lat) ** 2)
    M, M0 = _meridional_arc(lat), _meridional_arc(LAT0)
    E = K0 * Nrad * (Aterm + (1 - T + C) * Aterm ** 3 / 6 + (5 - 18 * T + T ** 2 + 72 * C - 58 * EP2) * Aterm ** 5 / 120)
    N = K0 * (M - M0 + Nrad * math.tan(lat) * (Aterm ** 2 / 2 + (5 - T + 9 * C + 4 * C ** 2) * Aterm ** 4 / 24
               + (61 - 58 * T + T ** 2 + 600 * C - 330 * EP2) * Aterm ** 6 / 720))
    return E, N


_M0 = _meridional_arc(LAT0)
_E1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))


def en_para_latlon(E, N):
    """(Easting, Northing) -> WGS84 lat/lon, formula inversa de Snyder.
    Validada por round-trip contra latlon_para_en, erro sub-metrico."""
    M = _M0 + N / K0
    mu = M / (A * (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256))
    phi1 = (mu
            + (3 * _E1 / 2 - 27 * _E1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * _E1 ** 2 / 16 - 55 * _E1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * _E1 ** 3 / 96) * math.sin(6 * mu)
            + (1097 * _E1 ** 4 / 512) * math.sin(8 * mu))

    C1 = EP2 * math.cos(phi1) ** 2
    T1 = math.tan(phi1) ** 2
    N1 = A / math.sqrt(1 - E2 * math.sin(phi1) ** 2)
    R1 = A * (1 - E2) / (1 - E2 * math.sin(phi1) ** 2) ** 1.5
    D = E / (N1 * K0)

    lat = phi1 - (N1 * math.tan(phi1) / R1) * (
        D ** 2 / 2
        - (5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * EP2) * D ** 4 / 24
        + (61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * EP2 - 3 * C1 ** 2) * D ** 6 / 720
    )
    lon = LON0 + (
        D - (1 + 2 * T1 + C1) * D ** 3 / 6
        + (5 - 2 * C1 + 28 * T1 - 3 * C1 ** 2 + 8 * EP2 + 24 * T1 ** 2) * D ** 5 / 120
    ) / math.cos(phi1)

    return math.degrees(lat), math.degrees(lon)


class Mosaico:
    """Junta os dois ficheiros GeoTIFF (duas quadriculas vizinhas) num unico
    array numpy, com metadados de georreferenciacao lidos das tags do
    proprio TIFF. Deteta sozinho qual dos dois ficheiros fica mais a norte
    (maior Northing/tiepoint Y) em vez de confiar na ordem dos nomes dados
    -- os nomes dos ficheiros da DGT nao indicam de forma fiavel qual e
    qual (ja tivemos um bug exatamente por assumir isso)."""

    def __init__(self, path_a, path_b):
        img_a = tifffile.TiffFile(path_a)
        img_b = tifffile.TiffFile(path_b)

        tags_a = {t.name: t.value for t in img_a.pages[0].tags}
        tags_b = {t.name: t.value for t in img_b.pages[0].tags}
        tiepoint_a = tags_a["ModelTiepointTag"]
        tiepoint_b = tags_b["ModelTiepointTag"]
        scale = tags_a["ModelPixelScaleTag"]

        grid_a = img_a.asarray().astype(np.float32)
        grid_b = img_b.asarray().astype(np.float32)

        # O ficheiro com o tiepoint Y (Northing) maior fica mais a norte --
        # empilha-se sempre por cima, independentemente do nome do ficheiro.
        if tiepoint_a[4] >= tiepoint_b[4]:
            grid_norte, tiepoint_norte = grid_a, tiepoint_a
            grid_sul = grid_b
        else:
            grid_norte, tiepoint_norte = grid_b, tiepoint_b
            grid_sul = grid_a

        self.origem_x = tiepoint_norte[3]
        self.origem_y = tiepoint_norte[4]
        self.pixel = scale[0]
        self.grid = np.vstack([grid_norte, grid_sul])

    def latlon_para_pixel(self, lat, lon):
        E, N = latlon_para_en(lat, lon)
        col = round((E - self.origem_x) / self.pixel)
        row = round((self.origem_y - N) / self.pixel)
        return row, col

    def pixel_para_latlon(self, row, col):
        E = self.origem_x + col * self.pixel
        N = self.origem_y - row * self.pixel
        return en_para_latlon(E, N)

    def dentro(self, row, col):
        return 0 <= row < self.grid.shape[0] and 0 <= col < self.grid.shape[1]


_mosaico_cache = {}


def _obter_mosaico(path_norte, path_sul):
    chave = (path_norte, path_sul)
    if chave not in _mosaico_cache:
        _mosaico_cache[chave] = Mosaico(path_norte, path_sul)
    return _mosaico_cache[chave]


def amostrar_linha(mosaico, p1, p2, n=200):
    r1, c1 = mosaico.latlon_para_pixel(*p1)
    r2, c2 = mosaico.latlon_para_pixel(*p2)
    celulas = set()
    for i in range(n + 1):
        t = i / n
        row = round(r1 + t * (r2 - r1))
        col = round(c1 + t * (c2 - c1))
        if mosaico.dentro(row, col):
            celulas.add((row, col))
    return celulas


def amostrar_poligonal(mosaico, pontos, n_por_segmento=200):
    if len(pontos) < 2:
        raise ValueError("A barreira precisa de pelo menos 2 pontos.")
    celulas = set()
    for p1, p2 in zip(pontos[:-1], pontos[1:]):
        celulas |= amostrar_linha(mosaico, p1, p2, n=n_por_segmento)
    return celulas


def amostrar_poligonal_com_posicao(mosaico, pontos, n_por_segmento=200):
    """Como amostrar_poligonal, mas devolve tambem a lista ORDENADA de
    (row, col, distancia_acumulada_m) ao longo da barreira -- para
    identificar que troco da barreira e realmente util."""
    amostras = []
    dist_acumulada = 0.0
    for p1, p2 in zip(pontos[:-1], pontos[1:]):
        E1, N1 = latlon_para_en(*p1)
        E2, N2 = latlon_para_en(*p2)
        comprimento_segmento = math.sqrt((E2 - E1) ** 2 + (N2 - N1) ** 2)
        r1, c1 = mosaico.latlon_para_pixel(*p1)
        r2, c2 = mosaico.latlon_para_pixel(*p2)
        for i in range(n_por_segmento + 1):
            t = i / n_por_segmento
            row = round(r1 + t * (r2 - r1))
            col = round(c1 + t * (c2 - c1))
            dist = dist_acumulada + t * comprimento_segmento
            if mosaico.dentro(row, col):
                amostras.append((row, col, dist))
        dist_acumulada += comprimento_segmento
    return amostras


def ponto_a_distancia_na_poligonal(pontos, distancia_alvo_m):
    dist_acumulada = 0.0
    for p1, p2 in zip(pontos[:-1], pontos[1:]):
        E1, N1 = latlon_para_en(*p1)
        E2, N2 = latlon_para_en(*p2)
        comprimento_segmento = math.sqrt((E2 - E1) ** 2 + (N2 - N1) ** 2)
        if dist_acumulada + comprimento_segmento >= distancia_alvo_m or math.isclose(comprimento_segmento, 0):
            t = 0.0 if comprimento_segmento == 0 else (distancia_alvo_m - dist_acumulada) / comprimento_segmento
            t = max(0.0, min(1.0, t))
            return (p1[0] + t * (p2[0] - p1[0]), p1[1] + t * (p2[1] - p1[1]))
        dist_acumulada += comprimento_segmento
    return pontos[-1]


def _celulas_para_3d(mosaico, mascara, max_celulas=20000):
    """Converte uma mascara booleana na lista de posicoes (x, z) reais
    dessas celulas, no mesmo referencial usado por converter_pontos_3d."""
    linhas, colunas = np.nonzero(mascara)
    n = len(linhas)
    if n == 0:
        return []
    if n > max_celulas:
        passo = int(np.ceil(n / max_celulas))
        linhas, colunas = linhas[::passo], colunas[::passo]
    return [
        {"x": float(c * mosaico.pixel), "z": float(r * mosaico.pixel)}
        for r, c in zip(linhas, colunas)
    ]


def _gerar_imagem_mancha(mosaico, visitado, margem_px=5):
    linhas, cols = np.nonzero(visitado)
    r_min = max(0, linhas.min() - margem_px)
    r_max = min(visitado.shape[0] - 1, linhas.max() + margem_px)
    c_min = max(0, cols.min() - margem_px)
    c_max = min(visitado.shape[1] - 1, cols.max() + margem_px)

    recorte = visitado[r_min:r_max + 1, c_min:c_max + 1]
    altura, largura = recorte.shape

    rgba = np.zeros((altura, largura, 4), dtype=np.uint8)
    rgba[recorte, 0] = 30
    rgba[recorte, 1] = 100
    rgba[recorte, 2] = 200
    rgba[recorte, 3] = 165

    img = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    imagem_base64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    lat_sw, lon_sw = mosaico.pixel_para_latlon(r_max, c_min)
    lat_ne, lon_ne = mosaico.pixel_para_latlon(r_min, c_max)
    bounds = [[lat_sw, lon_sw], [lat_ne, lon_ne]]

    return imagem_base64, bounds


def calcular_charca(mosaico, barreira_pontos, montante, altura_barragem):
    if len(barreira_pontos) < 2:
        raise ValueError("A barreira precisa de pelo menos 2 pontos.")

    comprimento_barreira_m = 0.0
    for p1, p2 in zip(barreira_pontos[:-1], barreira_pontos[1:]):
        E1, N1 = latlon_para_en(*p1)
        E2, N2 = latlon_para_en(*p2)
        comprimento_barreira_m += math.sqrt((E2 - E1) ** 2 + (N2 - N1) ** 2)

    amostras_barreira = amostrar_poligonal_com_posicao(mosaico, barreira_pontos)
    barreira_celulas = {(r, c) for r, c, _ in amostras_barreira}
    if not barreira_celulas:
        raise ValueError("A linha da barreira cai fora da area coberta pelos ficheiros.")

    seed = mosaico.latlon_para_pixel(*montante)
    if not mosaico.dentro(*seed):
        raise ValueError("O ponto a montante cai fora da area coberta pelos ficheiros.")
    if seed in barreira_celulas:
        raise ValueError("O ponto a montante cai em cima da barreira -- escolhe um ponto claramente dentro do vale.")

    cota_barreira = min(mosaico.grid[r, c] for r, c in barreira_celulas)
    nivel_agua = cota_barreira + altura_barragem

    cota_montante = mosaico.grid[seed]
    if cota_montante > nivel_agua:
        raise ValueError(
            f"O ponto a montante (cota {cota_montante:.1f}m) esta acima do nivel de agua "
            f"calculado ({nivel_agua:.1f}m) -- escolhe um ponto mais fundo no vale."
        )

    n_linhas, n_cols = mosaico.grid.shape
    visitado = np.zeros(mosaico.grid.shape, dtype=bool)
    fila = deque([seed])
    visitado[seed] = True
    tocou_borda = False

    while fila:
        row, col = fila.popleft()
        if row in (0, n_linhas - 1) or col in (0, n_cols - 1):
            tocou_borda = True
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = row + dr, col + dc
            if not (0 <= nr < n_linhas and 0 <= nc < n_cols):
                continue
            if visitado[nr, nc] or (nr, nc) in barreira_celulas:
                continue
            if mosaico.grid[nr, nc] <= nivel_agua:
                visitado[nr, nc] = True
                fila.append((nr, nc))

    n_celulas = int(visitado.sum())
    area_celula = mosaico.pixel ** 2
    area_m2 = n_celulas * area_celula
    profundidades = nivel_agua - mosaico.grid[visitado]
    volume_m3 = float(profundidades.sum() * area_celula)
    profundidade_max = float(profundidades.max()) if n_celulas else 0.0

    n_linhas_grid, n_cols_grid = mosaico.grid.shape

    def adjacente_a_inundacao(row, col):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = row + dr, col + dc
                if 0 <= nr < n_linhas_grid and 0 <= nc < n_cols_grid and visitado[nr, nc]:
                    return True
        return False

    posicoes_uteis = [dist for (row, col, dist) in amostras_barreira if adjacente_a_inundacao(row, col)]

    barreira_otimizada = None
    comprimento_barreira_util_m = None
    if posicoes_uteis:
        dist_min, dist_max = min(posicoes_uteis), max(posicoes_uteis)
        p_inicio = ponto_a_distancia_na_poligonal(barreira_pontos, dist_min)
        p_fim = ponto_a_distancia_na_poligonal(barreira_pontos, dist_max)
        comprimento_barreira_util_m = dist_max - dist_min
        barreira_otimizada = [p_inicio, p_fim]

    imagem_base64, bounds = _gerar_imagem_mancha(mosaico, visitado)
    celulas_3d = _celulas_para_3d(mosaico, visitado)

    return {
        "cota_barreira_m": round(float(cota_barreira), 2),
        "comprimento_barreira_m": round(comprimento_barreira_m, 1),
        "comprimento_barreira_util_m": round(comprimento_barreira_util_m, 1) if comprimento_barreira_util_m is not None else None,
        "barreira_otimizada": barreira_otimizada,
        "nivel_agua_m": round(float(nivel_agua), 2),
        "area_inundada_m2": round(area_m2, 1),
        "area_inundada_ha": round(area_m2 / 10000, 3),
        "volume_m3": round(volume_m3, 1),
        "profundidade_maxima_m": round(profundidade_max, 2),
        "flood_atingiu_borda_dos_dados": tocou_borda,
        "mancha_imagem_png_base64": imagem_base64,
        "mancha_bounds": bounds,
        "celulas_3d": celulas_3d,
        "celulas_3d_tamanho_m": mosaico.pixel,
    }


def montar_conclusao(barreira_pontos, montante, altura_barragem,
                      path_norte=TIF_NORTE_DEFAULT, path_sul=TIF_SUL_DEFAULT):
    limitations = [
        "Calculo geometrico sobre o MDT LiDAR (2m) -- nao substitui um projeto "
        "de engenharia hidraulica real (estabilidade da barreira, permeabilidade "
        "do solo, evaporacao, caudal afluente, licenciamento).",
        "Assume que a barreira bloqueia toda a largura do vale de forma "
        "impermeavel ate a altura indicada -- na pratica a construcao real "
        "teria de confirmar isso no terreno.",
    ]
    try:
        resultado = calcular_charca(_obter_mosaico(path_norte, path_sul), barreira_pontos, montante, altura_barragem)
    except Exception as e:
        return {
            "engine": "Charca",
            "question": "Que volume de água fica represado com esta barreira?",
            "answer": None,
            "knowledge_level": "INFERENCE",
            "confidence": {"label": "Baixa", "reason": str(e)},
            "limitations": [str(e)],
            "sources": ["DGT -- Levantamento LiDAR de Portugal Continental (MDT 2m)"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    if resultado["flood_atingiu_borda_dos_dados"]:
        limitations.insert(0,
            "ATENCAO: a area inundada calculada toca a borda dos ficheiros "
            "carregados -- a represa real pode estender-se para alem da area "
            "que temos dados, o que significa que este volume e um MINIMO, "
            "nao o valor real. Carrega quadriculas adicionais a volta para confirmar."
        )
        confianca = "Baixa"
    else:
        confianca = "Média"

    return {
        "engine": "Charca",
        "question": "Que volume de água fica represado com esta barreira?",
        "answer": resultado,
        "knowledge_level": "INFERENCE",
        "confidence": {
            "label": confianca,
            "reason": "Cálculo geométrico direto sobre o MDT LiDAR (2m de resolução) -- alta precisão geométrica, mas não é um projeto de engenharia.",
        },
        "limitations": limitations,
        "sources": ["DGT -- Levantamento LiDAR de Portugal Continental (MDT 2m)"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------
# Vista 3D -- exportacao da grelha reduzida + conversao de pontos GPS
# ---------------------------------------------------------------------
def converter_pontos_3d(mosaico, pontos_latlon):
    """Converte pontos GPS para (x, z, elevacao) no mesmo referencial usado
    pela malha 3D -- x = metros a leste do canto noroeste (col*pixel),
    z = metros a sul do canto noroeste (row*pixel)."""
    resultado = []
    for lat, lon in pontos_latlon:
        row, col = mosaico.latlon_para_pixel(lat, lon)
        if not mosaico.dentro(row, col):
            resultado.append(None)
            continue
        resultado.append({
            "x": col * mosaico.pixel,
            "z": row * mosaico.pixel,
            "elevacao": float(mosaico.grid[row, col]),
        })
    return resultado


def exportar_elevacao_3d(mosaico, fator_reducao=8):
    grid_reduzido = mosaico.grid[::fator_reducao, ::fator_reducao]
    n_linhas, n_cols = grid_reduzido.shape

    lat_nw, lon_nw = mosaico.pixel_para_latlon(0, 0)
    lat_ne, lon_ne = mosaico.pixel_para_latlon(0, mosaico.grid.shape[1] - 1)
    lat_sw, lon_sw = mosaico.pixel_para_latlon(mosaico.grid.shape[0] - 1, 0)
    lat_se, lon_se = mosaico.pixel_para_latlon(mosaico.grid.shape[0] - 1, mosaico.grid.shape[1] - 1)

    return {
        "n_linhas": n_linhas,
        "n_cols": n_cols,
        "pixel_m": mosaico.pixel * fator_reducao,
        "elevacoes": grid_reduzido.round(1).tolist(),
        "elevacao_min": float(grid_reduzido.min()),
        "elevacao_max": float(grid_reduzido.max()),
        "cantos": {
            "noroeste": [lat_nw, lon_nw], "nordeste": [lat_ne, lon_ne],
            "sudoeste": [lat_sw, lon_sw], "sudeste": [lat_se, lon_se],
        },
        # Retangulo exato no MESMO referencial usado pela malha 3D -- ao
        # contrario dos 'cantos' em GPS acima, isto nao tem nenhuma rotacao
        # ao ser usado para pedir uma imagem alinhada pixel a pixel com o
        # terreno. NOTA: este referencial nao inclui o false easting/
        # northing padrao do EPSG:3763 (ver nota no topo do ficheiro) --
        # se o pedido a um servico externo com bboxSR=3763 nao alinhar
        # corretamente, e o primeiro sitio a rever.
        "bbox_3763": {
            "xmin": mosaico.origem_x,
            "xmax": mosaico.origem_x + (n_cols - 1) * mosaico.pixel * fator_reducao,
            "ymin": mosaico.origem_y - (n_linhas - 1) * mosaico.pixel * fator_reducao,
            "ymax": mosaico.origem_y,
        },
    }
