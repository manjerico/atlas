# Atlas — Protótipo integrado (Silves)

Backend Flask que junta seis motores (Jurídico, Energético, Agronómico,
Hídrico, Ambiental e Planeamento Agrícola) por trás de rotas simples, mais
ferramentas de charca, terraplanagem e vista 3D do terreno, e serve o mapa
interativo.

## Como correr

1. Instala as dependências:
   ```
   pip install -r requirements.txt
   ```
   (em Mac, se `pip` não funcionar, tenta `pip3 install -r requirements.txt`)

2. Corre o servidor:
   ```
   python app.py
   ```
   (em Mac: `python3 app.py`)

3. Abre no browser: **http://localhost:5000**

4. Dá zoom no mapa até veres os limites das parcelas, e clica dentro de uma.

## Estrutura

- `app.py` — servidor Flask com todas as rotas
- `motor_juridico.py` — motor jurídico (SIG de Silves + cadastro DGT)
- `motor_solar.py` — motor energético (PVGIS + EU-DEM)
- `motor_agricola.py` — motor agronómico (SoilGrids + EU-DEM)
- `motor_hidrico.py` — motor hídrico (SIG de Silves + Open-Meteo + LNEG)
- `motor_ambiental.py` — motor ambiental (risco de incêndio, faixa legal de
  gestão de combustível, distância a estradas)
- `motor_charca.py` — cálculo de volume de charcas (barreira em arco +
  montante, MDT LiDAR 2m) + transformações de coordenadas + vista 3D
- `motor_terraplanagem.py` — cálculo de corte/aterro sobre uma área
  desenhada (MDT LiDAR 2m)
- `motor_agricultura.py` — área cultivável, necessidades de rega (FAO-56),
  compatibilidade solo/clima vs. cultura
- `templates/index.html` — a página do mapa, incluindo a vista 3D (Three.js)
- `data/*.tif` — os dois ficheiros do MDT LiDAR (2m) de Silves

## Porque é que isto precisava de um backend

O Motor Jurídico, sozinho, conseguia correr direto no browser porque o
serviço SIG de Silves permite pedidos de outras origens (CORS). O PVGIS
(usado pelo Motor Energético) **proíbe explicitamente** esse tipo de pedido
vindo de um browser — por isso essa chamada tinha de passar a viver aqui,
no backend, e o browser passa a falar só com este servidor.

## Nota importante sobre os dois ficheiros LiDAR (data/*.tif)

O `motor_charca.py` deteta AUTOMATICAMENTE qual dos dois ficheiros fica
mais a norte (comparando as suas coordenadas internas), em vez de assumir
isso pelo nome do ficheiro — já tivemos um bug real por confiar no nome.
Não é preciso te preocupares com a ordem em que os passas.

## Limitações a saber

- Isto só cobre o concelho de Silves — os IDs de camadas são específicos
  deste município.
- Charca, Terraplanagem, Planeamento Agrícola e Vista 3D só funcionam
  dentro da área coberta pelos dois ficheiros `.tif` em `data/` — fora
  dessa área dão erro "fora dos dados".
- O servidor Flask corre em modo de desenvolvimento por omissão — em
  produção (Render, etc.) usa `gunicorn app:app`, nunca `debug=True`
  publicamente.
- O Motor Ambiental **não gera rotas de fuga dinâmicas** — em caso de
  incêndio real, liga sempre 112 e segue a Proteção Civil/GNR/bombeiros.
- O Motor de Planeamento Agrícola nunca recomenda uma cultura, nem estima
  produção/rendimento/retorno — só compatibilidade técnica e necessidades
  de rega pela metodologia publicada FAO-56.
- Todos os motores continuam a ter os limites documentados nos comentários
  de cada ficheiro — nenhum substitui o parecer de um técnico (agrónomo,
  jurista, engenheiro) antes de uma decisão de investimento real.

## Nota sobre esta versão

Este projeto foi reconstruído a partir do histórico da conversa depois de
uma perda do ambiente de trabalho local. A lógica de backend foi
revalidada célula a célula contra os ficheiros LiDAR reais (mesmos
resultados de antes da perda). A interface (`templates/index.html`) foi
reconstruída com cuidado mas não pôde ser testada num browser real antes
da entrega — vale a pena testar com atenção redobrada desta vez.
