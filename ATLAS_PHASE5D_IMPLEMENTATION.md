# ATLAS V2 — Phase 5D Implementation

**Estado:** IMPLEMENTADA / VALIDADA LOCALMENTE  
**Âmbito:** comunicação, exportação e relatórios  
**Especificação de produto:** `ATLAS_PHASE5_PRODUCT_SPEC.md`  
**Arquitetura vinculativa:** `ATLAS_V2_ARCHITECTURE.md`

## 1. Resultado

A alternativa ativa pode agora ser comunicada através de:

- vista 2D enquadrada pela área atualmente visível no mapa;
- vista 3D indicativa e estável gerada a partir do MDT;
- captura da câmara 3D atual, diretamente no modal 3D;
- imagem limpa da proposta;
- relatório PDF simples;
- relatório técnico PDF criado apenas por pedido explícito.

As imagens incluem projeto, alternativa, legenda ou contexto, data e aviso de caráter preliminar quando aplicável.

## 2. Relatório simples

O relatório simples inclui:

- identificação do projeto e alternativa;
- objetivo da leitura;
- imagem 2D e imagem 3D;
- objetos principais e parâmetros resumidos;
- métricas resumidas;
- quatro semáforos com respetivas razões;
- fontes de dados;
- limitações;
- validações profissionais recomendadas.

O documento não escolhe uma alternativa nem apresenta os resultados como finais.

## 3. Relatório técnico

O relatório técnico só é gerado através da ação `Gerar relatório técnico`. Acrescenta:

- CRS e bounding box;
- identidades, versões de snapshot e proveniência dos objetos;
- geometrias GeoJSON e parâmetros;
- resultados completos por motor;
- `parameters_used`;
- warnings, erros e limitações;
- estado stale explícito;
- referência TM06 / EPSG:3763, resolução, redução de amostra e cobertura MDT;
- avaliação explicável atual com limitações por dimensão.

## 4. Renderização de imagens

A exportação 2D usa o enquadramento Leaflet atual, transmitido ao backend pelo `ProjectStore`, e produz uma imagem independente de tiles externos. A imagem limpa usa o enquadramento integral da proposta.

A vista 3D exportada no painel é uma representação isométrica reproduzível do MDT e dos objetos. O modal 3D permite ainda exportar a câmara atual. Se a captura WebGL não estiver disponível, o Atlas usa a representação isométrica como fallback.

Nenhuma imagem exportada altera geometrias ou cria persistência paralela.

## 5. Política de linguagem

A interface e os documentos usam expressões como `estimativa`, `indicação`, `aparente`, `dados disponíveis`, `requer validação` e `estudo preliminar`.

Os documentos declaram que não substituem levantamento topográfico, projeto de arquitetura ou engenharia, parecer técnico, licenciamento ou confirmação junto das entidades competentes.

Foi realizada uma revisão heurística da linguagem e da hierarquia visual. Um teste moderado com participantes reais não foi simulado nem declarado; permanece uma atividade externa de validação de produto.

## 6. Fronteiras frontend/backend

Foram acrescentadas duas operações V2:

- `GET /api/v2/projects/{project_id}/scenarios/{scenario_id}/exports/image`;
- `GET /api/v2/projects/{project_id}/scenarios/{scenario_id}/exports/report`.

Os downloads V2 passam por `ProjectStore.requestBlob()`. Os componentes de UI não fazem `fetch()` direto para estes endpoints.

## 7. Testes e validação

O gate local final terminou com:

- 23 testes Python aprovados;
- validação das assinaturas e anexos de três PNG;
- validação de PDF simples e técnico;
- relatório técnico de quatro páginas, A4, renderizado e inspecionado página a página;
- texto, fontes, limitações e identificação stale confirmados;
- sintaxe Python e JavaScript aprovada;
- download do relatório simples validado no browser local;
- captura da vista 3D atual validada no browser local;
- layout normal e 700 × 820 px validado;
- zero erros ou warnings na consola;
- `git diff --check` sem erros.

O smoke test realizado é local. Não foi criado commit, push ou deploy e não é declarado qualquer teste no Render. O smoke test remoto deverá ser executado depois de uma publicação autorizada.

## 8. Dependência

Foi acrescentado `reportlab` a `requirements.txt` para gerar PDF no backend. Não foi introduzida qualquer dependência ou framework frontend.

## 9. Compatibilidade arquitetural

A Phase 5D preserva Flask, Vanilla JS, Leaflet, Three.js, SQLite, os modelos persistentes, `SimulationResult`, GeoJSON, TM06 / EPSG:3763, adapters V1, `ProjectStore` como fronteira V2 e o fluxo legado da charca.

As exportações são artefactos transitórios gerados a pedido. Não foi criada uma entidade persistente de relatório ou simulação.

Não foi necessário reabrir nenhuma decisão congelada em `ATLAS_V2_ARCHITECTURE.md`.

