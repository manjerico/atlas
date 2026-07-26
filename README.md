# Atlas — Protótipo integrado (Silves)

Backend Flask que junta quatro motores (Jurídico, Energético, Agronómico e
Hídrico) por trás de rotas simples, e serve o mapa interativo.

## Como correr

1. Instala as dependências (só precisas do Flask):
   ```
   pip install flask
   ```
   (em Mac, se `pip` não funcionar, tenta `pip3 install flask`)

2. Corre o servidor:
   ```
   python app.py
   ```
   (em Mac: `python3 app.py`)

3. Abre no browser: **http://localhost:5000**

4. Dá zoom no mapa até veres os limites das parcelas, e clica dentro de uma.

## Estrutura

- `app.py` — servidor Flask, com as rotas `/api/motor-juridico`, `/api/motor-solar`, `/api/motor-agricola` e `/api/motor-hidrico`
- `motor_juridico.py` — lógica do motor jurídico (SIG de Silves + cadastro DGT)
- `motor_solar.py` — lógica do motor energético (PVGIS + EU-DEM)
- `motor_agricola.py` — lógica do motor agronómico (SoilGrids + EU-DEM)
- `motor_hidrico.py` — lógica do motor hídrico (SIG de Silves + Open-Meteo)
- `templates/index.html` — a página do mapa

## Porque é que isto precisava de um backend

O Motor Jurídico, sozinho, conseguia correr direto no browser porque o
serviço SIG de Silves permite pedidos de outras origens (CORS). O PVGIS
(usado pelo Motor Energético) **proíbe explicitamente** esse tipo de pedido
vindo de um browser — por isso essa chamada tinha de passar a viver aqui,
no backend, e o browser passa a falar só com este servidor, nunca
diretamente com o PVGIS ou com o EU-DEM.

## Limitações a saber

- Isto só cobre o concelho de Silves — os IDs de camadas do motor jurídico
  são específicos deste município.
- O servidor Flask corre em modo de desenvolvimento (`debug=True`) — nunca
  publiques isto na internet tal como está; serve só para testar localmente.
- Todos os motores continuam a ter os mesmos limites já documentados nos
  comentários de cada ficheiro (`motor_juridico.py`, `motor_solar.py`,
  `motor_agricola.py`, `motor_hidrico.py`) — em particular, nenhum deles
  substitui o parecer de um técnico (agrónomo, jurista, engenheiro) antes
  de uma decisão de investimento real.
