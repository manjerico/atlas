"""
Atlas - Motor Charca / Barragem v0 (prototipo)

Calcula o volume de agua armazenado ao colocar uma barreira (represa) numa
linha de agua, usando o MDT LiDAR da DGT (2m de resolucao) -- muito mais
preciso que o EU-DEM (25m) usado nos outros motores, por isso construido
a parte, a partir de ficheiros descarregados manualmente do Centro de
Dados da DGT (nao ha API publica para este LiDAR, ao contrario das outras
fontes usadas no Atlas).

Requisitos: dois ficheiros GeoTIFF do MDT (2m), adjacentes em Y (norte/sul),
cobrindo a zona de interesse. Usa apenas tifffile + numpy (sem GDAL/rasterio,
que nao estao disponiveis neste ambiente) -- a conversao de coordenadas
GPS -> EPSG:3763 (ETRS89 / Portugal TM06) e feita manualmente com as
formulas padrao de Mercator Transversa (Snyder), parametros confirmados
em epsg.io.

Metodo:
  1. Mosaico dos dois ficheiros (norte + sul).
  2. A linha da barreira e amostrada na grelha -- a cota mais baixa nessa
     linha define o "leito" no local da barragem.
  3. Nivel de agua = cota mais baixa da barreira + altura da barragem.
  4. Enchimento por inundacao (flood fill), a partir de um ponto a montante,
     por todas as celulas ligadas com cota <= nivel de agua, sem atravessar
     a linha da barreira.
  5. Volume = soma, por celula inundada, de (nivel_agua - cota_celula) * area_celula.

Uso:
    python motor_charca.py <tif_norte> <tif_sul> \
        <lat_barreira1> <lon_barreira1> <lat_barreira2> <lon_barreira2> \
        <lat_montante> <lon_montante> <altura_barragem_m>
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

_DIR = os.path.dirname(os.path.abspath(__file__))
TIF_NORTE_DEFAULT = os.path.join(_DIR, "data", "MDT-2m-184044-04-2024_v01.tif")
TIF_SUL_DEFAULT = os.path.join(_DIR, "data", "MDT-2m-184043-04-2024_v01.tif")

_mosaico_cache = None

# --- Parametros EPSG:3763 (ETRS89 / Portugal TM06), confirmados via epsg.io ---
A = 6378137.0
INV_F = 298.257222101
F = 1.0 / INV_F
E2 = 2 * F - F ** 2
EP2 = E2 / (1 - E2)
LAT0 = math.radians(39.66825833333333)
LON0 = math.radians(-8.133108333333334)
K0 = 1.0


def _meridional_arc(lat):
    return A * (
        (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256) * lat
        - (3 * E2 / 8 + 3 * E2 ** 2 / 32 + 45 * E2 ** 3 / 1024) * math.sin(2 * lat)
        + (15 * E2 ** 2 / 256 + 45 * E2 ** 3 / 1024) * math.sin(4 * lat)
        - (35 * E2 ** 3 / 3072) * math.sin(6 * lat)
    )


def latlon_para_en(lat_deg, lon_deg):
    """WGS84 lat/lon -> EPSG:3763 (Easting, Northing), formulas de Snyder."""
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
    """EPSG:3763 (Easting, Northing) -> WGS84 lat/lon, formula inversa de Snyder.
    Testada por round-trip contra latlon_para_en (ver validacao no historico
    de desenvolvimento) -- erro sub-metrico para pontos dentro de Portugal
    continental."""
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
    def __init__(self, path_norte, path_sul):
        norte = tifffile.imread(path_norte)
        sul = tifffile.imread(path_sul)
        self.grid = np.vstack([norte, sul]).astype(np.float64)
        self.origem_x, self.origem_y = self._ler_tiepoint(path_norte)
        self.pixel = 2.0  # metros

    @staticmethod
    def _ler_tiepoint(path):
        tf = tifffile.TiffFile(path)
        tie = tf.pages[0].tags['ModelTiepointTag'].value
        return tie[3], tie[4]  # world_x, world_y do pixel (0,0)

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


def amostrar_linha(mosaico, p1, p2, n=200):
    """Amostra elevacoes ao longo de uma linha entre dois pontos lat/lon."""
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
    """Amostra elevacoes ao longo de uma linha poligonal com varios pontos
    (permite barreiras em arco/curva, nao so uma reta entre 2 pontos --
    cada par de pontos consecutivos e tratado como mais um segmento reto)."""
    if len(pontos) < 2:
        raise ValueError("A barreira precisa de pelo menos 2 pontos.")
    celulas = set()
    for p1, p2 in zip(pontos[:-1], pontos[1:]):
        celulas |= amostrar_linha(mosaico, p1, p2, n=n_por_segmento)
    return celulas


def calcular_bacia_natural(mosaico, seed_latlon, incremento_registo=0.25, max_celulas=25000):
    """Cresce uma bacia a partir de um unico ponto (seed), sempre pela celula
    disponivel mais baixa a seguir (algoritmo 'priority flood', tecnica
    padrao de hidrologia de terreno). Ao contrario do modo manual (barreira +
    montante), aqui NAO se especifica uma barreira -- e o proprio relevo que
    determina onde a bacia natural termina, o que evita o problema de a
    'charca' se espalhar por areas enormes por causa de uma barreira mal
    posicionada.

    Devolve uma curva nivel/area/volume (para varias alturas de agua), nao
    um unico numero -- o utilizador escolhe depois a que fizer mais sentido.
    """
    seed = mosaico.latlon_para_pixel(*seed_latlon)
    if not mosaico.dentro(*seed):
        raise ValueError("O ponto cai fora da área coberta pelos ficheiros.")

    grid = mosaico.grid
    n_linhas, n_cols = grid.shape
    area_celula = mosaico.pixel ** 2

    visitado = np.zeros(grid.shape, dtype=bool)
    heap = [(float(grid[seed]), seed[0], seed[1])]
    visitado[seed] = True

    sum_elev = 0.0
    n_visitado = 0
    proximo_registo = math.floor(float(grid[seed]) / incremento_registo) * incremento_registo + incremento_registo

    curva = []
    tocou_borda = False
    atingiu_limite_celulas = False
    ultima_cota_valida = float(grid[seed])

    while heap:
        cota, row, col = heapq.heappop(heap)

        if row in (0, n_linhas - 1) or col in (0, n_cols - 1):
            tocou_borda = True
            break  # nao sabemos o que ha para alem dos dados -- parar aqui

        # Regista os niveis ja ultrapassados ANTES de somar esta celula --
        # esta celula tem cota >= proximo_registo (foi por isso que saiu do
        # heap agora), por isso ainda nao deve contar para o volume a esse
        # nivel mais baixo.
        while proximo_registo <= cota:
            if n_visitado > 0:
                volume = (proximo_registo * n_visitado - sum_elev) * area_celula
                curva.append({
                    "nivel_agua_m": round(proximo_registo, 2),
                    "area_ha": round(n_visitado * area_celula / 10000, 3),
                    "volume_m3": round(max(volume, 0), 1),
                })
            proximo_registo += incremento_registo

        sum_elev += cota
        n_visitado += 1
        ultima_cota_valida = cota

        if n_visitado >= max_celulas:
            atingiu_limite_celulas = True
            break

        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = row + dr, col + dc
            if 0 <= nr < n_linhas and 0 <= nc < n_cols and not visitado[nr, nc]:
                visitado[nr, nc] = True
                heapq.heappush(heap, (float(grid[nr, nc]), nr, nc))

    # Ponto final: o maior nivel totalmente contido que conseguimos validar
    volume_final = (ultima_cota_valida * n_visitado - sum_elev) * area_celula
    if not curva or curva[-1]["nivel_agua_m"] < round(ultima_cota_valida, 2):
        curva.append({
            "nivel_agua_m": round(ultima_cota_valida, 2),
            "area_ha": round(n_visitado * area_celula / 10000, 3),
            "volume_m3": round(max(volume_final, 0), 1),
        })

    imagem_base64, bounds = _gerar_imagem_mancha(mosaico, visitado & (grid <= ultima_cota_valida))

    return {
        "curva": curva,
        "nivel_maximo_contido_m": round(ultima_cota_valida, 2),
        "tocou_borda_dos_dados": tocou_borda,
        "atingiu_limite_seguranca": atingiu_limite_celulas,
        "mancha_imagem_png_base64": imagem_base64,
        "mancha_bounds": bounds,
    }


def amostrar_poligonal_com_posicao(mosaico, pontos, n_por_segmento=200):
    """Como amostrar_poligonal, mas devolve tambem a lista ORDENADA de
    (row, col, distancia_acumulada_m) ao longo da barreira -- para depois
    conseguirmos identificar que troço da barreira e realmente util
    (esta em contacto com a agua) e sugerir uma barreira mais curta."""
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
    """Devolve o ponto lat/lon que fica a 'distancia_alvo_m' ao longo da
    poligonal definida por 'pontos' (interpola dentro do segmento certo)."""
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

    cota_barreira = min(mosaico.grid[r, c] for r, c in barreira_celulas)
    nivel_agua = cota_barreira + altura_barragem

    seed = mosaico.latlon_para_pixel(*montante)
    if not mosaico.dentro(*seed):
        raise ValueError("O ponto a montante cai fora da area coberta pelos ficheiros.")
    if mosaico.grid[seed] > nivel_agua:
        raise ValueError(
            f"O ponto a montante (cota {mosaico.grid[seed]:.1f}m) esta acima do nivel de "
            f"agua calculado ({nivel_agua:.1f}m) -- escolhe um ponto mais fundo no vale."
        )

    visitado = np.zeros(mosaico.grid.shape, dtype=bool)
    fila = deque([seed])
    visitado[seed] = True
    tocou_borda = False
    n_linhas, n_cols = mosaico.grid.shape

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

    # Que troco da barreira desenhada esta mesmo em contacto com a agua
    # inundada? O resto nao esta a bloquear nada, e dispensavel.
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
        "mancha_bounds": bounds,  # [[lat_sw, lon_sw], [lat_ne, lon_ne]]
        "celulas_3d": celulas_3d,
        "celulas_3d_tamanho_m": mosaico.pixel,
    }


def _celulas_para_3d(mosaico, mascara, max_celulas=20000):
    """Converte uma mascara booleana (ex: celulas inundadas, ou celulas de
    corte/aterro) na lista de posicoes (x, z) reais dessas celulas, no
    mesmo referencial usado por converter_pontos_3d -- para desenhar em 3D
    seguindo a FORMA REAL da area (ex: o leito do vale), em vez de um
    retangulo que cobre tambem encosta seca a volta."""
    linhas, colunas = np.nonzero(mascara)
    n = len(linhas)
    if n == 0:
        return []
    if n > max_celulas:
        passo = int(np.ceil(n / max_celulas))
        linhas, colunas = linhas[::passo], colunas[::passo]
    return [
        {"x": float(c * mosaico.pixel), "z": float(r * mosaico.pixel)}
        for r, c in zip(colunas, linhas)
    ]


def _gerar_imagem_mancha(mosaico, visitado, margem_px=5):
    """Recorta a mascara de celulas inundadas a volta da sua bounding box,
    e devolve um PNG (azul semi-transparente) em base64 + os limites
    geograficos (lat/lon) desse recorte, para desenhar como imageOverlay
    no Leaflet."""
    linhas, cols = np.nonzero(visitado)
    r_min = max(0, linhas.min() - margem_px)
    r_max = min(visitado.shape[0] - 1, linhas.max() + margem_px)
    c_min = max(0, cols.min() - margem_px)
    c_max = min(visitado.shape[1] - 1, cols.max() + margem_px)

    recorte = visitado[r_min:r_max + 1, c_min:c_max + 1]
    altura, largura = recorte.shape

    rgba = np.zeros((altura, largura, 4), dtype=np.uint8)
    rgba[recorte, 0] = 30    # R
    rgba[recorte, 1] = 100   # G
    rgba[recorte, 2] = 200   # B
    rgba[recorte, 3] = 165   # A (semi-transparente)

    img = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    imagem_base64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    # Cantos do recorte -- note-se que a imagem no Leaflet e colocada como
    # um retangulo alinhado a lat/lon (Norte-Sul/Este-Oeste), enquanto a
    # grelha esta alinhada ao sistema de coordenadas projetado (EPSG:3763).
    # Para a area pequena de uma charca (algumas centenas de metros), o
    # desvio entre os dois alinhamentos e visualmente insignificante.
    lat_sw, lon_sw = mosaico.pixel_para_latlon(r_max, c_min)
    lat_ne, lon_ne = mosaico.pixel_para_latlon(r_min, c_max)
    bounds = [[lat_sw, lon_sw], [lat_ne, lon_ne]]

    return imagem_base64, bounds


def converter_pontos_3d(mosaico, pontos_latlon):
    """Converte pontos GPS para a posicao (x, z, elevacao) no MESMO referencial
    usado pela malha 3D exportada por exportar_elevacao_3d -- x = metros a
    leste do canto noroeste, z = metros a sul do canto noroeste, elevacao
    lida da grelha completa (2m), nao da reduzida usada so para desenho.
    O frontend faz depois a mesma translacao de centragem que ja aplica a
    malha (largura/2, profundidade/2), por isso aqui devolvemos coordenadas
    'cruas', antes de centrar."""
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
    """Exporta uma versao reduzida da grelha de elevacao (para nao pesar no
    browser) mais os limites geograficos, para desenhar um terreno 3D no
    frontend (Three.js). fator_reducao=8 e um bom equilibrio entre detalhe
    e performance (grelha de ~1000x500 -> ~125x62 pontos)."""
    grid_reduzido = mosaico.grid[::fator_reducao, ::fator_reducao]
    n_linhas, n_cols = grid_reduzido.shape

    lat_nw, lon_nw = mosaico.pixel_para_latlon(0, 0)
    lat_ne, lon_ne = mosaico.pixel_para_latlon(0, (n_cols - 1) * fator_reducao)
    lat_sw, lon_sw = mosaico.pixel_para_latlon((n_linhas - 1) * fator_reducao, 0)
    lat_se, lon_se = mosaico.pixel_para_latlon((n_linhas - 1) * fator_reducao, (n_cols - 1) * fator_reducao)

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
    }


def _obter_mosaico(path_norte, path_sul):
    global _mosaico_cache
    if _mosaico_cache is None:
        _mosaico_cache = Mosaico(path_norte, path_sul)
    return _mosaico_cache


def montar_conclusao_auto(ponto, path_norte=TIF_NORTE_DEFAULT, path_sul=TIF_SUL_DEFAULT):
    limitations = [
        "Deteção automática por 'priority flood' -- cresce sempre pela célula "
        "mais baixa disponível, sem simular hidrologia real (infiltração, "
        "evaporação, caudal afluente).",
        "Não substitui um projeto de engenharia hidráulica real antes de "
        "construir qualquer barreira.",
    ]
    try:
        resultado = calcular_bacia_natural(_obter_mosaico(path_norte, path_sul), ponto)
    except Exception as e:
        return {
            "engine": "Charca",
            "question": "Que bacias naturais existem perto deste ponto, e que volumes atingem?",
            "answer": None,
            "knowledge_level": "INFERENCE",
            "confidence": {"label": "Baixa", "reason": str(e)},
            "limitations": [str(e)],
            "sources": ["DGT -- Levantamento LiDAR de Portugal Continental (MDT 2m)"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    if resultado["tocou_borda_dos_dados"]:
        limitations.insert(0,
            "A bacia detetada toca a borda dos ficheiros carregados -- pode "
            "continuar para além da área com dados. A curva mostrada é válida "
            "até ao último nível confirmado, mas pode haver mais capacidade "
            "por confirmar."
        )
        confianca = "Baixa"
    elif resultado["atingiu_limite_seguranca"]:
        limitations.insert(0,
            f"A bacia ultrapassou o limite de segurança de área considerado "
            f"razoável para uma charca privada -- pode ser um vale maior do "
            f"que o esperado. Volumes mostrados são um MÍNIMO, não o total."
        )
        confianca = "Média"
    else:
        confianca = "Média"

    return {
        "engine": "Charca",
        "question": "Que bacia natural existe neste ponto, e que volumes atinge a diferentes alturas?",
        "answer": {
            "curva_nivel_area_volume": resultado["curva"],
            "nivel_maximo_contido_m": resultado["nivel_maximo_contido_m"],
            "mancha_imagem_png_base64": resultado["mancha_imagem_png_base64"],
            "mancha_bounds": resultado["mancha_bounds"],
        },
        "knowledge_level": "INFERENCE",
        "confidence": {
            "label": confianca,
            "reason": (
                "Baseado em MDT LiDAR de 2m e crescimento automático pela célula "
                "mais baixa disponível -- identifica a bacia de forma objetiva, "
                "mas continua a ser uma simplificação geométrica."
            ),
        },
        "limitations": limitations,
        "sources": ["DGT -- Levantamento LiDAR de Portugal Continental (MDT 2m)"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
            "question": "Que volume de agua ficaria represado com esta barreira?",
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
            "nao o valor real. Carrega quadriculas adicionais a volta para "
            "confirmar."
        )
        confianca = "Baixa"
    else:
        confianca = "Media"

    return {
        "engine": "Charca",
        "question": "Que volume de agua ficaria represado com esta barreira?",
        "answer": resultado,
        "knowledge_level": "INFERENCE",
        "confidence": {
            "label": confianca,
            "reason": (
                "Baseado em MDT LiDAR de 2m -- boa resolucao geometrica, mas o "
                "calculo em si e uma simplificacao (bathtub fill), sem simular "
                "hidrologia real."
            ),
        },
        "limitations": limitations,
        "sources": ["DGT -- Levantamento LiDAR de Portugal Continental (MDT 2m)"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    if len(sys.argv) != 8:
        print("Uso: python motor_charca.py "
              "<lat_b1> <lon_b1> <lat_b2> <lon_b2> <lat_montante> <lon_montante> <altura_m>")
        print(f"(usa por omissao os ficheiros em {os.path.join(_DIR, 'data')})")
        sys.exit(1)
    b1 = (float(sys.argv[1]), float(sys.argv[2]))
    b2 = (float(sys.argv[3]), float(sys.argv[4]))
    montante = (float(sys.argv[5]), float(sys.argv[6]))
    altura = float(sys.argv[7])
    print(json.dumps(montar_conclusao(b1, b2, montante, altura), indent=2, ensure_ascii=False))
