# ATLAS V2 — Phase 5B Implementation

**Estado:** IMPLEMENTADA / VALIDADA LOCALMENTE  
**Âmbito:** planeamento guiado de uma implantação de edifício  
**Especificação de produto:** `ATLAS_PHASE5_PRODUCT_SPEC.md`  
**Arquitetura vinculativa:** `ATLAS_V2_ARCHITECTURE.md`

## 1. Resultado

A Phase 5B acrescenta um percurso guiado que permite a uma pessoa sem formação SIG:

1. escolher um modelo inicial de edifício;
2. ajustar dimensões, pisos, altura e orientação;
3. indicar a tolerância relativa à movimentação de terras;
4. posicionar o edifício com um clique no mapa;
5. rever a implantação, a plataforma associada e um acesso inicial;
6. aceitar ou rejeitar os elementos opcionais;
7. guardar os elementos na alternativa ativa;
8. obter uma estimativa preliminar de corte e aterro para a plataforma.

Não foi criada uma entidade persistente `BuildingProposal`. O resultado é guardado exclusivamente como `ScenarioObject` genérico dos tipos `building`, `platform` e `access`.

## 2. Modelos configuráveis

O Type Registry define quatro presets:

| Modelo | Dimensões iniciais | Pisos | Altura inicial |
|---|---:|---:|---:|
| Casa térrea | 10 × 14 m | 1 | 3,4 m |
| Casa de dois pisos | 9 × 11 m | 2 | 6,6 m |
| Armazém | 14 × 24 m | 1 | 6,0 m |
| Anexo | 6 × 8 m | 1 | 3,0 m |

Os presets são pontos de partida editáveis, não tipologias legais, projetos de arquitetura ou garantias de viabilidade.

## 3. Geração geométrica

As dimensões são aplicadas em metros no referencial físico já usado pelo V1. O módulo de planeamento:

- converte o centro WGS84 para o plano TM06 usado pelo MDT;
- constrói um retângulo orientado com largura e comprimento reais;
- converte a geometria novamente para GeoJSON WGS84;
- gera uma plataforma retangular com margem configurada;
- encontra o ponto mais próximo no limite da BaseParcel;
- cria um acesso direto entre esse ponto e o centro da implantação.

Todas as geometrias passam pela validação V2 existente. Geometrias inválidas ou totalmente fora da BaseParcel são rejeitadas. Geometrias parcialmente fora produzem warning.

## 4. Persistência e identidade

O bundle é persistido atomicamente como objetos independentes:

- `building` — implantação e parâmetros configurados;
- `platform` — área associada ao edifício;
- `access` — proposta inicial de ligação ao limite da parcela.

Plataforma e acesso guardam `building_object_id` e `proposal_ref` apenas nos respetivos parâmetros. Não existe sincronização automática entre estes objetos.

Cada objeto mantém a sua identidade própria de `ScenarioObject`. A duplicação de uma alternativa continua a usar o comportamento congelado de cenários e cria novas identidades na cópia.

## 5. Terraplanagem

Quando a plataforma é aceite:

- o `EarthworkAdapter` preservado executa o motor V1;
- o resultado referencia exclusivamente o `scenario_object_id` da plataforma;
- o resultado é persistido como `SimulationResult`;
- corte, aterro, saldo e cota-alvo permanecem estimativas preliminares;
- as limitações do adapter continuam anexadas ao resultado.

O assistente não cria um motor novo nem altera o algoritmo V1.

## 6. Acesso inicial

O acesso da Phase 5B é deliberadamente simples:

- liga a implantação ao ponto mais próximo do limite da parcela;
- guarda comprimento e largura indicativos;
- pode ser rejeitado antes de guardar;
- pode ser redesenhado posteriormente com a edição V2 existente.

Não otimiza ainda declive, curvas, drenagem, atravessamentos, propriedade de caminhos ou movimentação de terras. Estas limitações são mostradas antes da gravação.

## 7. Experiência 2D e 3D

### 2D

- preview tracejado antes de persistir;
- ponto de implantação destacado;
- estilos próprios para edifício, plataforma e acesso;
- enquadramento automático da BaseParcel ao abrir um projeto;
- edição posterior através do fluxo existente de redesenho;
- seleção e resultados no painel de proposta.

### 3D

- o edifício é apresentado como um volume simples com largura, comprimento, altura e orientação;
- plataforma e acesso permanecem como sobreposições no terreno;
- seleção continua partilhada através do `ProjectStore`;
- o renderer não possui persistência paralela.

O volume 3D é uma representação conceptual, não um modelo arquitetónico ou BIM.

## 8. Fronteiras frontend/backend

Foram acrescentadas duas operações V2:

- `POST /api/v2/projects/{project_id}/planning/building-preview`;
- `POST /api/v2/projects/{project_id}/scenarios/{scenario_id}/planning/building-proposal`.

O preview não persiste dados. A segunda operação volta a gerar e validar a proposta antes de a guardar.

Toda a comunicação V2 do assistente passa pelos métodos `previewBuildingProposal()` e `createGuidedBuildingProposal()` do `ProjectStore`. A UI não executa `fetch()` direto para estas operações.

## 9. Testes e validação

Foram acrescentados testes para:

- presets e schema do tipo `building`;
- preview não persistente;
- geração de edifício, plataforma e acesso;
- associação dos objetos ao edifício;
- persistência atómica no cenário;
- criação do resultado de terraplanagem;
- rejeição de localização totalmente fora da BaseParcel.

Resultado local final:

- 17 testes Python aprovados;
- sintaxe de `static/project_store.js` aprovada;
- sintaxe dos scripts incorporados em `templates/index.html` aprovada;
- fluxo completo validado no browser local;
- visualização 2D e 3D validada;
- layout estreito a 700 × 820 px validado;
- zero erros ou warnings na consola durante o percurso testado.

O teste visual usou uma BaseParcel temporária e uma base SQLite temporária. Não alterou a base de dados normal do utilizador.

## 10. Limitações conscientes

- o assistente posiciona o edifício no mapa 2D; o 3D permite visualizar e selecionar, mas ainda não arrastar a implantação;
- o acesso é uma linha direta, não uma otimização de percurso;
- não são calculados afastamentos legais, índices urbanísticos ou implantação admissível;
- não existe dimensionamento estrutural, geotécnico, de fundações ou drenagem;
- a plataforma é uma margem geométrica inicial;
- a estimativa de terras depende da cobertura e resolução do MDT;
- não existe estimativa detalhada de custos;
- a comparação explicada entre alternativas pertence à Phase 5C.

## 11. Compatibilidade arquitetural

A Phase 5B preserva:

- Flask, Vanilla JS, Leaflet e Three.js;
- `ProjectStore` como fronteira frontend/backend V2;
- SQLite e o schema existente;
- `ProjectObject`, `ScenarioObject` e `SimulationResult`;
- identidades próprias de `ScenarioObject`;
- GeoJSON e TM06 / EPSG:3763;
- rejeição de geometrias inválidas;
- adapter V1 de terraplanagem;
- fluxo legado da charca V1;
- caráter lazy e project-session scoped do `TerrainContext`.

Não foi necessário reabrir nenhuma decisão congelada em `ATLAS_V2_ARCHITECTURE.md`.

## 12. Próxima etapa

A próxima etapa recomendada é a Phase 5C — Apoio à decisão:

1. comparar pelo menos duas alternativas do mesmo projeto;
2. usar resultados atuais e identificar explicitamente resultados stale;
3. apresentar adequação, terras, relevo e condicionantes com razões;
4. usar cinzento quando os dados são insuficientes;
5. manter toda a linguagem como orientação preliminar, nunca como aprovação ou parecer final.
