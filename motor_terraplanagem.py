"""
Atlas - Motor Terraplanagem v0

Calcula corte/aterro (cut and fill) para nivelar uma area desenhada pelo
utilizador, usando o mesmo MDT LiDAR (2m) do motor da charca.

Metodologia: cota-alvo = MEDIA das cotas dentro do poligono. Para cada
celula: se cota atual > cota-alvo, e "corte"; se < cota-alvo, e "aterro".

O que isto NAO faz (Nivel 2, nao Nivel 3): nao inclui fator de
empolamento/compactacao, nem custo de maquinaria/mao de obra/transporte.
"""

import json
import math
from datetime import datetime, timezone
import numpy as np

from motor_charca import (
    _obter_mosaico, TIF_NORTE_DEFAULT, TIF_SUL_DEFAULT,
)
from PIL import Image
import io
import base64


def _pontos_dentro_poligono(rows, cols, poligono_rc):
    """Teste ponto-em-poligono vetorizado (ray casting, regra par-impar)."""
    n = len(poligono_rc)
    dentro = np.zeros(rows.shape, dtype=bool)
    j = n - 1
    for i in range(n):
        ri, ci = poligono_rc[i]
        rj, cj = poligono_rc[j]
        cond = ((ci > cols) != (cj > cols))
        denom = (cj - ci) if (cj - ci) != 0 else 1e-12
        x_intersecao = (rj - ri) * (cols - ci) / denom + ri
        cond = cond & (rows < x_intersecao)
        dentro = dentro ^ cond
        j = i
    return dentro


def calcular_terraplanagem(mosaico, poligono_latlon):
    if len(poligono_latlon) < 3:
        raise ValueError("São necessários pelo menos 3 pontos para definir uma área.")

    poligono_rc = [mosaico.latlon_para_pixel(lat, lon) for lat, lon in poligono_latlon]
    for r, c in poligono_rc:
        if not mosaico.dentro(r, c):
            raise ValueError("Uma ou mais pontos do polígono caem fora da área coberta pelos ficheiros.")

    rows_poly = [p[0] for p in poligono_rc]
    cols_poly = [p[1] for p in poligono_rc]
    margem = 2
    r_min = max(0, min(rows_poly) - margem)
    r_max = min(mosaico.grid.shape[0] - 1, max(rows_poly) + margem)
    c_min = max(0, min(cols_poly) - margem)
    c_max = min(mosaico.grid.shape[1] - 1, max(cols_poly) + margem)

    rows_grid, cols_grid = np.mgrid[r_min:r_max + 1, c_min:c_max + 1]
    dentro = _pontos_dentro_poligono(rows_grid, cols_grid, poligono_rc)

    n_celulas = int(dentro.sum())
    if n_celulas == 0:
        raise ValueError("O polígono não cobre nenhuma célula de dados (é demasiado pequeno?).")

    area_celula = mosaico.pixel ** 2
    cotas = mosaico.grid[r_min:r_max + 1, c_min:c_max + 1][dentro]
    cota_alvo = float(cotas.mean())

    diffs = cotas - cota_alvo
    volume_corte = float(np.sum(diffs[diffs > 0]) * area_celula)
    volume_aterro = float(np.sum(-diffs[diffs < 0]) * area_celula)
    area_total_m2 = n_celulas * area_celula

    sub_grid = mosaico.grid[r_min:r_max + 1, c_min:c_max + 1]
    corte_mask = dentro & (sub_grid > cota_alvo)
    aterro_mask = dentro & (sub_grid < cota_alvo)

    altura, largura = dentro.shape
    rgba = np.zeros((altura, largura, 4), dtype=np.uint8)
    rgba[corte_mask, 0] = 230; rgba[corte_mask, 1] = 126; rgba[corte_mask, 2] = 34; rgba[corte_mask, 3] = 175
    rgba[aterro_mask, 0] = 41; rgba[aterro_mask, 1] = 128; rgba[aterro_mask, 2] = 185; rgba[aterro_mask, 3] = 175

    img = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    imagem_base64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    lat_sw, lon_sw = mosaico.pixel_para_latlon(r_max, c_min)
    lat_ne, lon_ne = mosaico.pixel_para_latlon(r_min, c_max)
    bounds = [[lat_sw, lon_sw], [lat_ne, lon_ne]]

    def _celulas_recorte_para_3d(mascara_recorte, max_celulas=15000):
        linhas, colunas = np.nonzero(mascara_recorte)
        n = len(linhas)
        if n == 0:
            return []
        if n > max_celulas:
            passo = int(np.ceil(n / max_celulas))
            linhas, colunas = linhas[::passo], colunas[::passo]
        return [
            {"x": float((c + c_min) * mosaico.pixel), "z": float((r + r_min) * mosaico.pixel)}
            for r, c in zip(linhas, colunas)
        ]

    return {
        "cota_alvo_m": round(cota_alvo, 2),
        "area_total_m2": round(area_total_m2, 1),
        "area_total_ha": round(area_total_m2 / 10000, 3),
        "volume_corte_m3": round(volume_corte, 1),
        "volume_aterro_m3": round(volume_aterro, 1),
        "saldo_m3": round(volume_corte - volume_aterro, 1),
        "mancha_imagem_png_base64": imagem_base64,
        "mancha_bounds": bounds,
        "celulas_corte_3d": _celulas_recorte_para_3d(corte_mask),
        "celulas_aterro_3d": _celulas_recorte_para_3d(aterro_mask),
        "celulas_3d_tamanho_m": mosaico.pixel,
    }


def montar_conclusao(poligono_latlon, path_norte=TIF_NORTE_DEFAULT, path_sul=TIF_SUL_DEFAULT):
    limitations = [
        "Cota-alvo definida como a MÉDIA das cotas da área -- não é a única "
        "opção (poderia nivelar-se para outra cota à escolha).",
        "Não inclui fator de empolamento/compactação da terra (tipicamente "
        "+15% a +30% de volume solto vs. compactado, varia com o solo).",
        "Não inclui custo de maquinaria, mão de obra, transporte, nem "
        "remoção de vegetação ou construções existentes.",
        "Baseado em MDT LiDAR de 2m -- não substitui um levantamento "
        "topográfico real para orçamento de obra.",
    ]
    try:
        mosaico = _obter_mosaico(path_norte, path_sul)
        resultado = calcular_terraplanagem(mosaico, poligono_latlon)
    except Exception as e:
        return {
            "engine": "Terraplanagem",
            "question": "Quanta terra é preciso mover para nivelar esta área?",
            "answer": None,
            "knowledge_level": "INFERENCE",
            "confidence": {"label": "Baixa", "reason": str(e)},
            "limitations": [str(e)],
            "sources": ["DGT -- Levantamento LiDAR de Portugal Continental (MDT 2m)"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "engine": "Terraplanagem",
        "question": "Quanta terra é preciso mover para nivelar esta área?",
        "answer": resultado,
        "knowledge_level": "INFERENCE",
        "confidence": {
            "label": "Média",
            "reason": (
                "Baseado em MDT LiDAR de 2m de resolução -- suficiente para "
                "uma triagem de ordem de grandeza, não para orçamento de obra."
            ),
        },
        "limitations": limitations,
        "sources": ["DGT -- Levantamento LiDAR de Portugal Continental (MDT 2m)"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
