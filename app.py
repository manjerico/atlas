"""
Atlas - Backend (Silves)

Junta todos os motores por tras de rotas simples, e serve o mapa
interativo. Ver README.md para mais detalhes de arquitetura.
"""

from flask import Flask, request, jsonify, render_template
import os

import motor_juridico
import motor_solar
import motor_agricola
import motor_hidrico
import motor_charca
import motor_terraplanagem
import motor_ambiental
import motor_agricultura

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/motor-juridico")
def api_motor_juridico():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return jsonify({"erro": "Parâmetros 'lat' e 'lon' são obrigatórios"}), 400
    try:
        resultado = motor_juridico.montar_conclusao(lat, lon)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"erro": str(e)}), 502


@app.route("/api/motor-solar")
def api_motor_solar():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    peakpower = request.args.get("peakpower", default=1.0, type=float)
    if lat is None or lon is None:
        return jsonify({"erro": "Parâmetros 'lat' e 'lon' são obrigatórios"}), 400
    try:
        resultado = motor_solar.montar_conclusao(lat, lon, peakpower=peakpower)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"erro": str(e)}), 502


@app.route("/api/motor-agricola")
def api_motor_agricola():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return jsonify({"erro": "Parâmetros 'lat' e 'lon' são obrigatórios"}), 400
    try:
        resultado = motor_agricola.montar_conclusao(lat, lon)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"erro": str(e)}), 502


@app.route("/api/motor-hidrico")
def api_motor_hidrico():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return jsonify({"erro": "Parâmetros 'lat' e 'lon' são obrigatórios"}), 400
    try:
        resultado = motor_hidrico.montar_conclusao(lat, lon)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"erro": str(e)}), 502


@app.route("/api/motor-ambiental")
def api_motor_ambiental():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return jsonify({"erro": "Parâmetros 'lat' e 'lon' são obrigatórios"}), 400
    try:
        resultado = motor_ambiental.montar_conclusao(lat, lon)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"erro": str(e)}), 502


@app.route("/api/motor-charca", methods=["POST"])
def api_motor_charca():
    dados = request.get_json(force=True, silent=True) or {}
    try:
        barreira = dados["barreira"]  # [[lat,lon], [lat,lon], ...] -- 2 ou mais pontos
        montante = dados["montante"]  # [lat,lon]
        altura = float(dados["altura"])
        pontos = [(float(p[0]), float(p[1])) for p in barreira]
        if len(pontos) < 2:
            raise ValueError
        m = (float(montante[0]), float(montante[1]))
    except (KeyError, IndexError, TypeError, ValueError):
        return jsonify({"erro": "Corpo inválido. Esperado: {barreira:[[lat,lon],[lat,lon],...], montante:[lat,lon], altura:number}"}), 400

    try:
        resultado = motor_charca.montar_conclusao(pontos, m, altura)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"erro": str(e)}), 502


@app.route("/api/motor-terraplanagem", methods=["POST"])
def api_motor_terraplanagem():
    dados = request.get_json(force=True, silent=True) or {}
    try:
        poligono = dados["poligono"]  # [[lat,lon], [lat,lon], ...]
        pontos = [(float(p[0]), float(p[1])) for p in poligono]
    except (KeyError, IndexError, TypeError, ValueError):
        return jsonify({"erro": "Corpo inválido. Esperado: {poligono:[[lat,lon],...]}"}), 400

    try:
        resultado = motor_terraplanagem.montar_conclusao(pontos)
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"erro": str(e)}), 502


@app.route("/api/elevacao-3d")
def api_elevacao_3d():
    try:
        resultado = motor_charca.exportar_elevacao_3d(
            motor_charca._obter_mosaico(motor_charca.TIF_NORTE_DEFAULT, motor_charca.TIF_SUL_DEFAULT)
        )
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"erro": str(e)}), 502


@app.route("/api/converter-3d", methods=["POST"])
def api_converter_3d():
    dados = request.get_json(force=True, silent=True) or {}
    try:
        pontos = [(float(p[0]), float(p[1])) for p in dados["pontos"]]
    except (KeyError, IndexError, TypeError, ValueError):
        return jsonify({"erro": "Corpo inválido. Esperado: {pontos:[[lat,lon],...]}"}), 400

    try:
        mosaico = motor_charca._obter_mosaico(motor_charca.TIF_NORTE_DEFAULT, motor_charca.TIF_SUL_DEFAULT)
        resultado = motor_charca.converter_pontos_3d(mosaico, pontos)
        return jsonify({"pontos": resultado})
    except Exception as e:
        return jsonify({"erro": str(e)}), 502


@app.route("/api/culturas")
def api_culturas():
    return jsonify({cid: c["nome"] for cid, c in motor_agricultura.CULTURAS.items()})


@app.route("/api/area-cultivavel", methods=["POST"])
def api_area_cultivavel():
    dados = request.get_json(force=True, silent=True) or {}
    try:
        poligono = [(float(p[0]), float(p[1])) for p in dados["poligono"]]
    except (KeyError, IndexError, TypeError, ValueError):
        return jsonify({"erro": "Corpo inválido. Esperado: {poligono:[[lat,lon],...]}"}), 400
    try:
        return jsonify(motor_agricultura.montar_conclusao_area_cultivavel(poligono))
    except Exception as e:
        return jsonify({"erro": str(e)}), 502


@app.route("/api/necessidades-rega")
def api_necessidades_rega():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    cultura = request.args.get("cultura", type=str)
    area_ha = request.args.get("area_ha", type=float)
    if None in (lat, lon, area_ha) or not cultura:
        return jsonify({"erro": "Parâmetros 'lat', 'lon', 'cultura' e 'area_ha' são obrigatórios"}), 400
    try:
        return jsonify(motor_agricultura.montar_conclusao_rega(lat, lon, cultura, area_ha))
    except Exception as e:
        return jsonify({"erro": str(e)}), 502


@app.route("/api/compatibilidade")
def api_compatibilidade():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    cultura = request.args.get("cultura", type=str)
    if lat is None or lon is None or not cultura:
        return jsonify({"erro": "Parâmetros 'lat', 'lon' e 'cultura' são obrigatórios"}), 400
    try:
        return jsonify(motor_agricultura.montar_conclusao_compatibilidade(lat, lon, cultura))
    except Exception as e:
        return jsonify({"erro": str(e)}), 502


if __name__ == "__main__":
    # Em produção (Render, etc.), a porta vem de uma variável de ambiente,
    # e o debug fica desligado por omissão -- deixar o modo debug ligado
    # numa app publicamente acessível é um risco de segurança real (o
    # depurador interativo do Flask permite executar código arbitrário).
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode, threaded=True)
