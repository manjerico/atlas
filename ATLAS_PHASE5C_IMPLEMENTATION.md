# ATLAS V2 — Phase 5C Implementation

**Estado:** IMPLEMENTADA / VALIDADA LOCALMENTE  
**Âmbito:** comparação explicável e apoio preliminar à decisão  
**Especificação de produto:** `ATLAS_PHASE5_PRODUCT_SPEC.md`  
**Arquitetura vinculativa:** `ATLAS_V2_ARCHITECTURE.md`

## 1. Resultado

A Phase 5C permite comparar pelo menos duas alternativas do mesmo projeto sem produzir um ranking automático ou declarar uma solução vencedora.

Cada alternativa apresenta quatro dimensões independentes:

- adequação ao objetivo;
- movimentação de terras;
- relevo aparente;
- condicionantes conhecidas.

Cada dimensão mostra estado, razão, dados utilizados, fontes, limitações e próximo passo recomendado. Quando não existem dados suficientes, o estado é cinzento. Resultados desatualizados continuam consultáveis, mas não são usados silenciosamente como atuais.

## 2. Semáforos e interpretação

Os estados verde, amarelo, vermelho e cinzento são sinais de triagem explicáveis. Não representam aprovação, conformidade legal, segurança de execução ou parecer profissional.

As classes de declive e intensidade de terraplanagem são heurísticas explícitas para estudo preliminar. Não são limites regulamentares, critérios de licenciamento ou garantias de viabilidade.

## 3. Condicionantes

O tipo `building` disponibiliza o adapter `site_constraints`. O adapter normaliza a informação dos motores V1 jurídico e ambiental sem alterar os motores originais.

O resultado inclui, quando disponível:

- classificação de solo;
- condicionantes e riscos identificados;
- risco de incêndio e histórico;
- distância indicativa a estrada;
- informação de faixa de gestão de combustível;
- confiança, fontes, data de origem e limitações.

A consulta atual é pontual, baseada no centroide da implantação. O próprio resultado informa esta limitação e remete para confirmação nas fontes e entidades competentes.

## 4. Adequação do relevo

A camada de relevo divide a BaseParcel numa grelha limitada e classifica apenas o declive aparente do MDT disponível. A interface apresenta legenda, dimensão da célula, resolução nativa e limitações.

Esta camada não avalia geologia, solos, fundações, drenagem, vegetação, acessos ou regras urbanísticas.

## 5. Persistência e contratos

A comparação é calculada a pedido e não é persistida. Utiliza apenas:

- `ScenarioObject` atuais;
- `SimulationResult` persistidos;
- staleness derivado pelo contrato existente;
- `TerrainContext` lazy do projeto.

Não foram criadas entidades de comparação, campos stale persistidos ou ligações diretas de resultados a `ProjectObject`.

## 6. Fronteiras frontend/backend

Foram acrescentadas duas operações V2:

- `GET /api/v2/projects/{project_id}/terrain/suitability`;
- `POST /api/v2/projects/{project_id}/comparison`.

Toda a comunicação V2 passa por `ProjectStore`. A UI não executa `fetch()` direto para estas operações.

## 7. Testes e validação

O gate da Phase 5C terminou com:

- 21 testes Python aprovados;
- sintaxe JavaScript aprovada;
- comparação de duas alternativas validada no browser local;
- dados em falta confirmados em cinzento;
- camada e legenda de relevo validadas visualmente;
- zero erros ou warnings na consola.

O browser usou um projeto e uma base SQLite temporários. Não alterou a base normal do utilizador.

## 8. Compatibilidade arquitetural

A Phase 5C preserva Flask, Vanilla JS, Leaflet, Three.js, SQLite, GeoJSON, TM06 / EPSG:3763, o Type Registry, a identidade própria de `ScenarioObject`, a persistência de `SimulationResult`, o staleness derivado, os adapters V1 e o fluxo legado da charca.

Não foi necessário reabrir nenhuma decisão congelada em `ATLAS_V2_ARCHITECTURE.md`.

