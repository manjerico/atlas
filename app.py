"""
Atlas - Backend do protótipo (Silves)

Junta o motor jurídico e o motor solar por trás de duas rotas simples, e
serve a página do mapa. Isto resolve o problema do PVGIS não poder ser
chamado diretamente do browser (proíbe AJAX/CORS) -- ao correr aqui, do
lado do servidor, deixa de ser um problema, porque quem fala com o PVGIS
é este programa Python, não o browser do utilizador.

Como correr:
    pip install flask
    python app.py

Depois abre no browser: http://localhost:5000
"""

from flask import Flask, request, jsonify, render_template
import os

import motor_juridico
import motor_solar
import motor_agricola
import motor_hidrico
import motor_charca
import motor_terraplanagem
import direcao_agua
import direcao_agua
import motor_ambiental

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


@app.route("/api/linhas-agua-direcao")
def api_linhas_agua_direcao():
    try:
        xmin = request.args.get("xmin", type=float)
        ymin = request.args.get("ymin", type=float)
        xmax = request.args.get("xmax", type=float)
        ymax = request.args.get("ymax", type=float)
        if None in (xmin, ymin, xmax, ymax):
            return jsonify({"erro": "Parâmetros xmin,ymin,xmax,ymax obrigatórios"}), 400
    except (TypeError, ValueError):
        return jsonify({"erro": "Parâmetros inválidos"}), 400

    try:
        resultado = direcao_agua.calcular_direcoes(xmin, ymin, xmax, ymax)
        return jsonify(resultado)
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
