# Atlas V2 — Phase 5A Technical Audit

**Documento:** `ATLAS_PHASE5A_TECHNICAL_AUDIT.md`  
**Fase:** 5A — Fundação 3D  
**Data:** 2026-08-21  
**Estado:** IMPLEMENTADA / VALIDAÇÃO LOCAL CONCLUÍDA  
**Referências:** `ATLAS_V2_ARCHITECTURE.md`, `ATLAS_PHASE5_PRODUCT_SPEC.md`

## 1. Objetivo

Auditar o 3D V1 preservado, verificar a sua adequação ao percurso V2 e implementar o menor protótipo integrado capaz de demonstrar:

- terreno recortado ao projeto;
- imagem aérea sobre relevo;
- objetos V2 sobre o terreno;
- seleção partilhada entre 2D e 3D;
- comunicação backend exclusivamente através do `ProjectStore` no percurso V2;
- desempenho aceitável com o MDT real disponível.

Esta fase não implementa ainda o assistente de edifícios da Phase 5B.

## 2. Inventário factual do 3D V1

### Backend legado

`GET /api/elevacao-3d`

- utiliza `motor_charca._obter_mosaico()`;
- carrega o mosaico completo dos dois MDT;
- reduz a grelha por um fator fixo;
- devolve elevações, dimensões, resolução, cantos e bounding box;
- não conhece `Project`, `BaseParcel`, `Scenario` ou `ProjectObject`.

`POST /api/converter-3d`

- converte uma lista de pontos WGS84 para o referencial local da malha completa;
- utiliza diretamente o mosaico V1;
- não está limitado ao projeto ativo.

### Frontend legado

O 3D encontra-se embebido em `templates/index.html` e utiliza:

- Three.js 0.128;
- OrbitControls;
- uma `BufferGeometry` para o terreno;
- cores por altitude;
- textura obtida através do serviço municipal ORTOS2023;
- linhas cadastrais consultadas diretamente no frontend;
- sobreposições específicas dos resultados V1 de charca e terraplanagem;
- estado global como `dados3D`, `cena3D`, `malha3D` e `texturaOrto3D`.

### Relação com Leaflet

- Leaflet e Three.js não partilhavam seleção;
- a abertura 3D não dependia do projeto ativo;
- objetos V2 não eram apresentados no 3D;
- a câmara 3D não alterava a vista Leaflet;
- o botão 3D existia entre os controlos clássicos do mapa.

### Coordenadas

O V1 utiliza internamente TM06 sem o false easting/northing oficial, de forma consistente com os GeoTIFF disponíveis.

Foi confirmada uma incompatibilidade externa factual:

- o serviço municipal ORTOS2023 declara `wkid: 3763`;
- a sua extensão publicada utiliza coordenadas sem os offsets oficiais;
- a extensão anunciada é aproximadamente `x=-36220…-310`, `y=-288720…-243900`;
- um pedido com EPSG:3763 formal, incluindo os offsets, cai fora dessa extensão e devolve uma imagem vazia.

A correção adotada preserva ambos os conceitos:

- `bbox_3763` contém a representação formal com offsets;
- `orthophoto_bbox` contém as coordenadas específicas exigidas por essa fonte municipal.

O CRS interno e a matemática de transformação não foram alterados.

## 3. Classificação de migração

| Componente | Estratégia | Fundamentação |
|---|---|---|
| Three.js e `BufferGeometry` | KEEP | Renderizam corretamente a grelha atual sem exigir nova framework |
| OrbitControls | KEEP | Suficiente para navegação orbital desktop na Phase 5A |
| Cores por altitude | KEEP | Fallback útil quando a imagem aérea está indisponível |
| Construção da malha no browser | ADAPT | Passa a consumir recorte do projeto, mantendo o algoritmo base |
| Fonte de elevação V1 global | ADAPT | Novo endpoint V2 usa `TerrainContext` e apenas o recorte necessário |
| Estado 3D global | ADAPT | Dados, abertura e modo visual passam a ser refletidos no `ProjectStore`; renderer continua local à UI |
| Rotas `/api/elevacao-3d` e `/api/converter-3d` | KEEP legado | Permanecem para compatibilidade V1; o percurso V2 deixa de depender delas |
| Consulta cadastral direta dentro do 3D | REFACTOR | No modo V2 é substituída por BaseParcel e objetos vindos do estado do projeto |
| Objetos e seleção | REFACTOR | Passam a usar identidades reais de `ProjectObject` ou `ScenarioObject` |
| Textura ORTOS2023 | ADAPT | Mantida, com bounding box específico da fonte e fallback por altitude |
| Modal 3D técnico | ADAPT | Convertido numa superfície visual de terreno com métricas e aviso preliminar |
| Novo motor geoespacial 3D | NÃO NECESSÁRIO | Não foi identificada limitação factual que justifique Cesium ou outra dependência nesta fase |

## 4. Implementação realizada

### 4.1 Recorte de terreno V2

Foi acrescentado:

`GET /api/v2/projects/{project_id}/terrain/mesh`

O endpoint:

- valida o projeto;
- aceita opcionalmente `scenario_id`;
- utiliza a BaseParcel e os objetos ativos para determinar o recorte;
- reutiliza o `TerrainContext` lazy e project-session scoped;
- limita a maior dimensão da malha a 180 amostras;
- devolve proveniência, resolução nativa e resolução visual;
- indica se a cobertura MDT é completa;
- projeta BaseParcel e objetos para o referencial local da malha;
- mantém a identidade dos objetos de cenário quando existe cenário ativo.

Não foi criada uma nova entidade persistente de terreno ou visualização.

### 4.2 TerrainContext

O `TerrainContext` passou a suportar:

- recorte conjunto de múltiplas geometrias;
- limites seguros da cobertura raster;
- redução adaptativa da grelha;
- projeção de Polygon, MultiPolygon, LineString e MultiLineString;
- amostragem de elevação para as linhas de sobreposição;
- metadados explícitos de fonte e limitações.

O MDT completo continua a não ser carregado para o percurso V2.

### 4.3 ProjectStore

O `ProjectStore` passou a possuir:

- estado transitório `terrainView`;
- `uiState.terrainViewOpen`;
- `uiState.terrainBaseMode`;
- método `loadTerrainMesh()`;
- invalidação do recorte quando projeto, cenário ou objetos mudam.

O renderer Three.js não executa `fetch()` para dados V2.

### 4.4 Interface 3D

A interface inclui agora:

- imagem aérea como modo inicial;
- modo alternativo por altitude;
- título do projeto e alternativa;
- cotas mínima e máxima;
- desnível;
- resolução visual;
- BaseParcel destacada;
- objetos do projeto ou cenário sobre o relevo;
- seleção de objetos 3D refletida em `ProjectStore.uiState.selectedObjectId`;
- aviso permanente de estudo preliminar;
- loading e erro contextualizados;
- regresso claro ao mapa 2D.

Quando não existe projeto aberto, o modo V1 continua disponível como fallback.

## 5. Medição do protótipo

Teste executado com uma BaseParcel dentro da cobertura real dos MDT:

| Métrica | Resultado observado |
|---|---:|
| Dimensão da grelha | 120 × 98 |
| Vértices | 11 760 |
| Resolução visual | 4 m |
| Tamanho JSON | 209,8 KB |
| Tempo local do endpoint | 41,4 ms |
| Cobertura MDT | completa |
| Sobreposições | BaseParcel + 1 objeto |

Estes valores são uma medição local indicativa, não um SLA.

## 6. Testes e validação

### Automatizados

- 13 testes executados;
- 13 testes aprovados;
- os 11 testes anteriores continuam aprovados;
- novo teste de recorte limitado e project-scoped;
- novo teste de identidade de `ScenarioObject` no 3D;
- `bbox_3763` formal e `orthophoto_bbox` específico validados separadamente.

### Frontend

- sintaxe de `static/project_store.js` válida;
- sintaxe do JavaScript inline válida;
- `git diff --check` sem erros;
- terreno e sobreposição renderizados no browser local;
- alternância para cores de altitude validada;
- métricas e aviso preliminar validados;
- consola sem erros ou warnings durante a validação executada.

### Ortofoto

Foi observado inicialmente um terreno branco ao usar o `bbox_3763` formal. Os metadados públicos do serviço demonstraram que a fonte municipal espera o referencial sem offsets.

Após a correção, foi confirmado localmente que `orthophoto_bbox` está integralmente dentro da extensão declarada pelo serviço. A repetição visual do pedido foi interrompida pela proteção de privacidade do browser, porque transmitiria a área exata do projeto ao serviço externo. Não foi tentado contornar essa proteção.

A ortofoto deve ser novamente validada visualmente num projeto autorizado ou no deploy, antes do fecho de release público da Phase 5A.

## 7. Limitações conhecidas

- a imagem aérea depende de um serviço externo municipal;
- a política de cache e disponibilidade da ortofoto não é controlada pelo Atlas;
- a malha 3D é uma aproximação visual reduzida;
- os polígonos são apresentados como sobreposições preliminares e ainda não têm manipulação 3D completa;
- a câmara 3D e o enquadramento Leaflet ainda não são sincronizados espacialmente;
- a seleção é sincronizada, mas editar diretamente vértices em 3D fica para a Phase 5B/iterações seguintes;
- o fallback V1 continua a possuir estado e chamadas diretas legadas;
- a existência de `project_store.js` na raiz é um duplicado não servido; o ficheiro ativo é `static/project_store.js`.

## 8. Decisão técnica

**Decisão:** ADAPTAR o renderer Three.js existente.

Three.js é suficiente para a fundação 3D e para o percurso vertical atualmente definido. Não existe evidência que justifique introduzir Cesium, Mapbox GL, MapLibre 3D ou outra framework nesta fase.

Esta decisão deve ser revista apenas se a Phase 5B demonstrar uma necessidade factual que o renderer atual não consiga satisfazer de forma segura, nomeadamente:

- edição geográfica 3D precisa;
- streaming de terrenos muito maiores;
- múltiplas fontes raster com reprojeção dinâmica;
- sincronização de câmara geoespacial avançada;
- desempenho insuficiente após otimização proporcional.

## 9. Compatibilidade arquitetural

Foram preservados:

- Flask;
- Vanilla JS;
- Leaflet;
- Three.js;
- ProjectStore como fronteira V2;
- GeoJSON;
- TM06 / EPSG:3763;
- TerrainContext lazy;
- SQLite e o domínio persistente existente;
- identidades próprias de `ScenarioObject`;
- V1 e os seus fluxos legados.

Nenhum schema SQLite foi alterado.

## 10. Próxima etapa recomendada

Depois da validação visual final da ortofoto, avançar para a Phase 5B com um percurso estreito:

1. introduzir o tipo genérico `building` no Type Registry;
2. criar modelos configuráveis básicos;
3. implementar o assistente progressivo;
4. posicionar e editar a implantação nas duas vistas;
5. gerar uma plataforma associada;
6. executar o adapter de terraplanagem existente;
7. manter todas as conclusões como estimativas preliminares.
