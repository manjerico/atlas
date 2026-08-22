# Atlas V2 — Phase 5 Product Specification

**Documento:** `ATLAS_PHASE5_PRODUCT_SPEC.md`  
**Fase:** 5 — Terrain Intelligence & Guided Planning  
**Estado:** APROVADO PARA PLANEAMENTO TÉCNICO  
**Data:** 2026-08-21  
**Especificação arquitetural de referência:** `ATLAS_V2_ARCHITECTURE.md`  
**Base funcional:** Phase 4 concluída e auditada em `ATLAS_PHASE4_COMPLETION_AUDIT.md`

## 1. Estatuto do documento

Este documento define o objetivo de produto, o percurso do utilizador, o âmbito funcional e os critérios de aceitação da Phase 5.

Não substitui nem reabre por preferência a arquitetura congelada do Atlas V2. As decisões persistentes de domínio, cenários, simulações, geometria, CRS, persistência e comunicação frontend/backend continuam regidas por `ATLAS_V2_ARCHITECTURE.md`.

A Phase 5 pode alterar código legado V1 ou V2 quando isso for necessário para melhorar materialmente a aplicação. Essas alterações devem:

- responder a uma necessidade funcional ou incompatibilidade factual demonstrável;
- preservar contratos não afetados;
- manter os motores físicos isolados através de adapters quando aplicável;
- ser acompanhadas por testes proporcionais ao risco;
- evitar refatorizações extensas sem benefício de produto verificável;
- documentar qualquer alteração necessária a uma decisão arquitetural congelada.

Este documento aprova a direção de produto. Não seleciona antecipadamente uma nova biblioteca 3D nem autoriza uma reescrita do frontend.

## 2. Visão da Phase 5

Transformar o Atlas numa ferramenta visual e orientada que permita a uma pessoa sem formação técnica:

1. introduzir ou localizar um terreno;
2. compreender o relevo e as condicionantes conhecidas;
3. criar uma proposta inicial de implantação;
4. observar essa proposta em 2D e 3D;
5. comparar alternativas através de critérios explicáveis;
6. produzir um resumo que possa ser discutido com um profissional.

O percurso vertical de sucesso é:

```text
DEFINIR TERRENO
      ↓
COMPREENDER EM 2D E 3D
      ↓
PLANEAR UM EDIFÍCIO
      ↓
GERAR PLATAFORMA E ACESSO
      ↓
COMPARAR ALTERNATIVAS
      ↓
EXPORTAR IMAGENS E RELATÓRIO
```

O 3D é uma nova superfície de compreensão e edição. Não é, isoladamente, o produto da Phase 5. O valor principal está na combinação de terreno, orientação progressiva, alternativas e explicações.

## 3. Utilizadores-alvo

### 3.1 Utilizador não técnico

Pessoa que possui, pretende adquirir ou estuda um terreno e quer compreender possibilidades antes de contratar ou consultar especialistas.

Necessita de:

- linguagem simples;
- orientação progressiva;
- contexto visual;
- prevenção de interpretações excessivamente definitivas;
- indicação clara dos próximos passos profissionais.

### 3.2 Utilizador técnico

Arquiteto, engenheiro, topógrafo, projetista, consultor agrícola ou outro profissional que utiliza o Atlas para triagem, exploração inicial ou comunicação com clientes.

Necessita de:

- métricas e pressupostos visíveis;
- proveniência e resolução dos dados;
- geometrias consistentes;
- relatório técnico opcional;
- separação inequívoca entre estudo preliminar e validação de projeto.

### 3.3 Prioridade de dispositivo

A experiência completa da Phase 5 é desktop-first.

Tablet e telemóvel devem continuar utilizáveis para consulta básica, mas não precisam de oferecer edição equivalente nesta fase. A organização da interface não deve impedir uma futura experiência móvel dedicada.

## 4. Resultados prioritários

As prioridades escolhidas para o produto são:

1. compreender o relevo e as características relevantes do terreno;
2. comparar propostas para o mesmo terreno.

O diagnóstico inicial deve destacar sobretudo:

- áreas potencialmente adequadas para construção, cultivo ou acessos;
- condicionantes legais e ambientais conhecidas.

Cotas, desnível, declive, orientação e outros indicadores físicos continuam disponíveis e fundamentam as recomendações, mas não devem dominar a experiência inicial.

## 5. Princípios de experiência

### 5.1 Paridade entre 2D e 3D

As vistas 2D e 3D têm igual importância funcional.

- os mesmos objetos devem existir nas duas vistas;
- a seleção ativa deve permanecer sincronizada;
- alterações persistidas numa vista devem refletir-se na outra;
- a aplicação deve orientar o utilizador para a vista mais adequada a cada operação;
- o 2D privilegia desenho, alinhamento e medição precisa;
- o 3D privilegia relevo, implantação, impacto e compreensão espacial.

O estado partilhado continua a pertencer ao `ProjectStore`. Leaflet e a vista 3D são consumidores desse estado e não fontes independentes de verdade.

### 5.2 Aparência inicial do 3D

A vista 3D deve abrir, por defeito, com imagem aérea aplicada sobre o relevo, inspirada na referência visual discutida durante a definição da fase.

A apresentação deve:

- manter o terreno como elemento dominante;
- utilizar controlos de navegação simples e previsíveis;
- apresentar métricas de forma discreta;
- evitar a aparência de software SIG excessivamente técnico;
- identificar a fonte e as condições de utilização da imagem aérea.

Modos analíticos de altitude, declive ou orientação podem ser adicionados posteriormente, sem bloquear o percurso principal.

### 5.3 Complexidade progressiva

O Atlas deve começar com perguntas e resultados simples e revelar opções técnicas apenas quando são relevantes.

Não deve apresentar ao utilizador uma lista extensa de motores, parâmetros internos ou operações desconectadas do objetivo que escolheu.

### 5.4 Explicabilidade

Uma recomendação deve incluir sempre os fatores que a favoreceram ou penalizaram. O Atlas não deve produzir uma pontuação global opaca.

## 6. Percurso principal da Phase 5

### 6.1 Introdução do terreno

O utilizador deve conseguir:

- pesquisar uma morada ou coordenadas e ajustar o limite;
- desenhar manualmente a BaseParcel;
- importar limites geográficos em formatos a selecionar no planeamento técnico, com prioridade para GeoJSON, KML, GPX e Shapefile.

A importação de levantamento topográfico, MDT próprio ou dados de drone é uma evolução avançada. A Phase 5 deve evitar decisões que tornem essa evolução desnecessariamente difícil, mas não precisa de a implementar no primeiro percurso vertical.

GeoJSON permanece o contrato interno e de API. TM06 / EPSG:3763 permanece o sistema interno de trabalho físico.

### 6.2 Leitura inicial do terreno

Depois de abrir o projeto, o Atlas deve apresentar:

- terreno 2D e 3D;
- cobertura e resolução conhecidas do MDT;
- amplitude de cotas e declive em linguagem acessível;
- zonas potencialmente mais ou menos adequadas para a intervenção escolhida;
- condicionantes conhecidas e respetiva proveniência;
- limitações ou ausência de dados.

O diagnóstico deve adaptar-se ao objetivo. Uma zona favorável para um edifício não é necessariamente favorável para uma charca ou para agricultura.

### 6.3 Assistente guiado

A primeira versão do assistente resolve uma intervenção de cada vez e fica preparada para evoluir até ao planeamento global da propriedade.

O primeiro percurso guiado é a implantação de um edifício.

O assistente deve recolher, em linguagem simples:

- tipo de edifício;
- dimensões aproximadas;
- número de pisos ou altura;
- orientação preferida, quando relevante;
- ponto ou limite de acesso desejado;
- preferências que afetem a implantação;
- tolerância relativa a movimentação de terras.

O utilizador deve poder ignorar campos não essenciais e regressar a passos anteriores sem perder o trabalho válido.

### 6.4 Edifícios configuráveis

Na primeira versão devem existir modelos configuráveis, pelo menos:

- casa térrea;
- edifício de dois pisos;
- armazém;
- anexo.

Um edifício deve ser representado por geometria geográfica e parâmetros configurados pelo Type Registry. Não deve ser criada uma hierarquia de classes de edifícios.

O planeamento técnico deve avaliar a introdução do tipo genérico `building` no Type Registry, com geometria e schema adequados. Esta extensão deve reutilizar `ProjectObject` e `ScenarioObject` sem criar novas entidades persistentes específicas.

### 6.5 Geração progressiva da proposta

Depois de posicionar ou gerar um edifício, o Atlas deve revelar progressivamente:

1. implantação e cotas do terreno;
2. plataforma provável;
3. estimativa de corte e aterro;
4. orientações ou cotas alternativas;
5. proposta de acesso;
6. comportamento de drenagem relevante para a implantação, quando suportado por dados e cálculo factual;
7. conflitos com condicionantes conhecidas.

O utilizador pode aceitar, editar ou rejeitar cada elemento gerado.

### 6.6 Proposta automática de acesso

O Atlas deve gerar uma proposta inicial de acesso ao edifício e permitir:

- redesenhar o trajeto;
- ajustar pontos de ligação;
- comparar alternativas;
- explicar fatores como distância, declive e movimentação de terras;
- acrescentar no futuro largura, inclinação máxima, curvas e drenagem.

Uma proposta automática não deve ser apresentada como acesso executável ou aprovado.

## 7. Alternativas e comparação

Cada alternativa persistente continua a ser representada por um `Scenario`, com `ScenarioObjects` independentes.

O assistente pode gerar mais do que uma alternativa, mas não deve criar uma entidade paralela de proposta fora do modelo de cenários.

A comparação principal deve apresentar vantagens e desvantagens com base em:

1. adequação ao objetivo escolhido;
2. movimentação de terras;
3. declive e estabilidade aparente, dentro do que os dados permitem inferir;
4. condicionantes legais e ambientais conhecidas.

Podem existir métricas auxiliares, mas estas quatro dimensões têm prioridade na interface.

### 7.1 Semáforo orientativo

Cada dimensão pode receber:

- **verde — favorável para estudo preliminar**;
- **amarelo — requer atenção ou validação adicional**;
- **vermelho — conflito ou risco relevante identificado nos dados disponíveis**;
- **cinzento — dados insuficientes ou análise indisponível**.

O semáforo não representa aprovação, conformidade legal, segurança de execução ou parecer profissional.

Cada cor deve ser acompanhada por:

- razões observadas;
- dados utilizados;
- limitações relevantes;
- ação recomendada para confirmar a indicação.

Exemplo:

> **Amarelo — requer validação adicional**  
> A implantação exige aterro significativo no modelo disponível e aproxima-se de uma condicionante cartografada. Confirme as cotas através de levantamento topográfico e valide a condicionante junto da entidade competente.

## 8. Condicionantes legais e ambientais

As condicionantes devem ser apresentadas através de fichas explicativas, não como conclusões jurídicas.

Cada ficha deve incluir, quando disponível:

- nome e categoria;
- descrição em linguagem simples;
- entidade ou fonte;
- data ou versão dos dados;
- cobertura e resolução relevantes;
- relação espacial observada com a proposta;
- limitações da consulta;
- indicação de onde ou com quem confirmar.

O Atlas não deve afirmar que uma operação está licenciada, dispensada de licença, legalmente permitida ou definitivamente proibida apenas com base numa camada cartográfica.

As ContextLayers mantêm o contrato arquitetural existente: são informativas, configuradas globalmente, com visibilidade específica por projeto, e não participam nos cenários.

## 9. Charca na Phase 5

A charca deve continuar disponível no fluxo factual seguro existente.

No percurso inicial da Phase 5, o utilizador deve poder:

- desenhar manualmente a área pretendida;
- observar a geometria em 2D e 3D;
- obter estimativas de área e, quando suportado de forma factual, volume;
- receber limitações e pedidos de validação profissional.

Ficam para uma evolução posterior:

- identificação automática de depressões;
- análise completa da bacia contributiva;
- sugestões automáticas de localização;
- simulação de diferentes níveis de água;
- análise de barragem, estabilidade, impermeabilização ou segurança.

O conflito factual já documentado permanece válido: o motor V1 utiliza barreira linear e ponto a montante, enquanto o objeto V2 `pond` é poligonal. A Phase 5 não deve criar um adapter artificial. Uma integração nova exige primeiro um contrato de domínio factual e seguro.

## 10. Exportação e relatórios

### 10.1 Imagens

O utilizador deve conseguir exportar:

- vista 2D atual;
- vista 3D atual;
- imagem limpa da proposta com identificação do cenário;
- legenda e data, quando aplicável.

### 10.2 Relatório simples

O relatório simples deve estar disponível diretamente e incluir:

- identificação do projeto e alternativa;
- mapa 2D e imagem 3D;
- objetivo da análise;
- objetos principais da proposta;
- métricas resumidas;
- semáforos e respetivas razões;
- fontes de dados;
- limitações;
- indicação de validações profissionais recomendadas.

### 10.3 Relatório técnico

O relatório técnico é criado apenas a pedido do utilizador e pode acrescentar:

- coordenadas e CRS;
- geometrias e parâmetros utilizados;
- cotas, perfis, áreas e volumes;
- resultados por motor;
- `parameters_used`;
- proveniência, resolução e cobertura dos dados;
- resultados desatualizados claramente identificados;
- limitações técnicas detalhadas.

O relatório não constitui projeto de execução, levantamento topográfico, parecer jurídico ou certificação profissional.

## 11. Política de resultados indicativos

### 11.1 Regra geral

Os resultados do Atlas são indicações para estudo preliminar. Não são valores finais, garantias, autorizações ou pareceres definitivos.

Esta regra aplica-se à interface, aos motores, aos semáforos, às comparações e aos relatórios.

### 11.2 Linguagem preferida

Utilizar:

- estimativa preliminar;
- indicação;
- potencialmente adequado;
- favorável para estudo preliminar;
- com base nos dados disponíveis;
- requer confirmação;
- nível de confiança;
- limitação conhecida.

Evitar, salvo quando se descreve um facto estritamente comprovado dentro do respetivo contrato:

- aprovado;
- garantido;
- seguro para construir;
- legalmente permitido;
- definitivamente proibido;
- valor exato;
- solução ótima;
- projeto validado.

### 11.3 Contexto obrigatório por resultado

Cada resultado relevante deve apresentar ou permitir consultar:

- fonte dos dados;
- data ou versão;
- resolução e cobertura, quando conhecidas;
- parâmetros efetivamente utilizados;
- estado `success`, `partial` ou `error` traduzido para linguagem útil;
- limitações e warnings;
- data de cálculo;
- indicação de resultado desatualizado quando `is_stale` for verdadeiro.

### 11.4 Aviso de referência

> **Indicação para estudo preliminar**  
> Este resultado baseia-se nos dados e pressupostos atualmente disponíveis. Não substitui levantamento topográfico, projeto de arquitetura ou engenharia, parecer técnico, licenciamento nem confirmação junto das entidades competentes.

O aviso geral não substitui limitações específicas por resultado.

## 12. Compatibilidade arquitetural

A Phase 5 mantém:

- Flask;
- Vanilla JS;
- Leaflet para a vista 2D;
- `ProjectStore` como única fronteira frontend → backend;
- SQLite como persistência inicial;
- `Project`, `BaseParcel`, `ProjectObject`, `Scenario`, `ScenarioObject` e `SimulationResult`;
- Type Registry como fonte de semântica dos objetos;
- GeoJSON como contrato de geometria;
- TM06 / EPSG:3763 para cálculo interno;
- TerrainContext lazy e project-session scoped;
- V1 engines integrados através de EngineAdapters;
- resultado mais recente por `ScenarioObject + engine`;
- staleness derivado por timestamps;
- isolamento de cenários e atualização explícita a partir do projeto.

Não são introduzidos por esta especificação:

- React, Vue ou Svelte;
- PostGIS;
- Redis;
- Celery;
- microserviços;
- uma nova hierarquia de entidades por tipo de objeto;
- sincronização automática entre `ProjectObject` e `ScenarioObject`;
- histórico persistente de execuções.

## 13. Gate técnico da visualização 3D

Antes da implementação completa deve ser criado um protótipo técnico curto com MDT real e imagem aérea.

O protótipo deve avaliar se o Three.js existente satisfaz:

- terreno com textura georreferenciada;
- precisão visual suficiente na área do projeto;
- sincronização de seleção e objetos com Leaflet;
- navegação fluida;
- edição básica de objetos;
- desempenho em computador comum;
- gestão de memória com os MDT atuais;
- captura de imagem;
- atribuição e licenciamento das fontes cartográficas.

Se o Three.js não satisfizer requisitos essenciais de forma segura ou sustentável, o planeamento técnico pode propor uma biblioteca geoespacial 3D dedicada. Essa proposta deve:

1. demonstrar a limitação factual;
2. comparar a alternativa com o stack atual;
3. avaliar peso, licenciamento, desempenho e integração;
4. preservar Vanilla JS e `ProjectStore`;
5. limitar a alteração à camada de visualização.

Nenhuma biblioteca nova é aprovada apenas por preferência estética.

## 14. Subfases

### Phase 5A — Fundação 3D

Entregáveis:

- protótipo técnico validado;
- terreno 3D com imagem aérea;
- alternância clara entre 2D e 3D;
- seleção e objetos sincronizados;
- navegação e estados vazios adequados a utilizadores não técnicos;
- desempenho medido com dados reais.

### Phase 5B — Planeamento guiado

Entregáveis:

- assistente de implantação de edifício;
- modelos configuráveis;
- criação e edição de alternativa;
- plataforma associada;
- estimativa de terraplanagem;
- proposta inicial de acesso;
- complexidade progressiva.

### Phase 5C — Apoio à decisão

Entregáveis:

- zonas potencialmente adequadas;
- comparação de pelo menos duas alternativas;
- semáforos explicáveis;
- fichas de condicionantes;
- proveniência e limitações visíveis;
- estado insuficiente/cinzento quando não existem dados adequados.

### Phase 5D — Comunicação

Entregáveis:

- exportação de imagens 2D e 3D;
- relatório PDF simples;
- relatório técnico a pedido;
- validação de linguagem e interpretação com utilizadores não técnicos;
- auditoria final e smoke test do deploy.

## 15. Critérios de aceitação

### 15.1 Percurso vertical

Uma pessoa sem formação SIG deve conseguir, sem editar dados internos:

1. definir ou importar um terreno;
2. abrir a vista 3D;
3. iniciar o assistente de edifício;
4. criar pelo menos duas alternativas;
5. compreender por que uma alternativa é mais ou menos favorável;
6. ajustar a proposta;
7. exportar uma imagem e um relatório simples.

### 15.2 Compreensão inicial

Num teste moderado, um novo utilizador deve conseguir identificar, em aproximadamente dez minutos:

- a forma geral do relevo;
- pelo menos uma zona potencialmente adequada;
- uma condicionante ou limitação relevante, quando exista;
- o caráter preliminar das conclusões.

### 15.3 Sincronização

- um objeto criado ou editado numa vista deve aparecer corretamente na outra;
- a identidade persistente do objeto não muda devido à troca de vista;
- a seleção ativa é coerente;
- não existe persistência paralela no renderer 3D;
- nenhuma chamada backend é feita fora do `ProjectStore`.

### 15.4 Comparação

- são comparáveis pelo menos duas alternativas do mesmo projeto;
- a comparação utiliza `ScenarioObjects` e resultados persistidos existentes;
- cada semáforo apresenta razões e limitações;
- dados insuficientes não são convertidos artificialmente em avaliação favorável ou desfavorável;
- resultados stale continuam visíveis, mas são identificados e não usados silenciosamente como atuais.

### 15.5 Segurança de interpretação

- não existem afirmações de aprovação, garantia ou conformidade não suportadas;
- relatórios contêm fontes e limitações;
- métricas físicas indicam unidades;
- a interface distingue estimativa, warning, erro e ausência de dados;
- qualquer recomendação de execução remete para validação profissional adequada.

## 16. Fora do âmbito inicial

Não fazem parte do primeiro percurso vertical da Phase 5:

- planeamento automático completo de toda a propriedade;
- análise avançada e automática de charcas;
- dimensionamento estrutural ou geotécnico;
- projeto de drenagem executável;
- estimativa detalhada de custos;
- importação de modelos BIM/CAD 3D;
- experiência móvel completa;
- colaboração multiutilizador;
- parecer jurídico automático;
- licenciamento;
- substituição de levantamento topográfico;
- garantia de adequação construtiva.

## 17. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| O 3D criar falsa sensação de precisão | Mostrar resolução, fontes, limitações e linguagem preliminar |
| Desempenho insuficiente com MDT e imagem aérea | Protótipo 5A, recorte por projeto, carregamento lazy e medição em equipamento comum |
| Inconsistência entre 2D e 3D | Estado exclusivo no ProjectStore e testes de sincronização |
| Imagem aérea sem licença ou atribuição adequada | Avaliação de fonte e licenciamento no gate técnico |
| Semáforos interpretados como aprovação | Razões, categoria cinzenta, aviso contextual e validação com utilizadores |
| Dados legais desatualizados | Fonte, data, versão, limitações e encaminhamento para entidade competente |
| Assistente gerar propostas inviáveis | Validação geométrica, critérios explícitos e possibilidade de rejeitar/editar |
| Crescimento excessivo da Phase 5 | Entrega sequencial 5A–5D e percurso vertical como limite de âmbito |
| Conflito com motor de charca V1 | Preservar fluxo seguro e exigir contrato factual antes de novo adapter |

## 18. Estratégia de teste

A Phase 5 deve acrescentar testes para:

- Type Registry e parâmetros de novos tipos;
- criação e edição de objetos do assistente;
- isolamento e comparação de cenários;
- cálculos ou heurísticas de adequação;
- proveniência, limitações e categoria de dados insuficientes;
- sincronização lógica 2D/3D;
- exportação e conteúdo mínimo dos relatórios;
- regressão dos 11 testes existentes;
- sintaxe JavaScript;
- validação visual e interativa em browser local;
- desempenho do 3D com MDT real;
- smoke test do Render após publicação autorizada.

Qualquer novo motor ou cálculo deve ter casos que evitem apresentar ausência de dados como resultado factual.

## 19. Decisões de produto recolhidas

| # | Questão | Decisão |
|---|---|---|
| 1 | Resultado inicial | Compreender o terreno; comparar propostas |
| 2 | Papel do 3D | Paridade e sincronização 2D/3D |
| 3 | Aparência 3D | Imagem aérea sobre o relevo |
| 4 | Diagnóstico | Adequação por objetivo e condicionantes |
| 5 | Intervenções prioritárias | Edifício, plataforma e charca |
| 6 | Comparação | Vantagens e desvantagens orientativas |
| 7 | Critérios | Objetivo, terras, declive/estabilidade e condicionantes |
| 8 | Automatização | Assistente guiado |
| 9 | Evolução do assistente | Uma intervenção primeiro; plano global no futuro |
| 10 | Comunicação de confiança | Semáforo explicado |
| 11 | Edição | Capacidade equivalente em 2D/3D com orientação contextual |
| 12 | Edifícios | Modelos configuráveis |
| 13 | Cálculo associado | Plataforma, alternativas, acesso, drenagem e condicionantes, progressivamente |
| 14 | Charca | Desenho/estimativa e evolução futura para sugestão/simulação |
| 15 | Acessos | Proposta automática editável e comparável |
| 16 | Condicionantes | Fichas com fonte, data e linguagem simples |
| 17 | Saídas | Imagens, PDF simples e relatório técnico a pedido |
| 18 | Dispositivos | Desktop primeiro; experiência móvel futura |
| 19 | Entrada de terreno | Desenho, pesquisa e ficheiros; topografia avançada depois |
| 20 | Definição de sucesso | Percurso vertical completo |

## 20. Próximo passo

O próximo deliverable é um plano técnico da Phase 5A que deve:

1. inventariar o código Three.js V1 atualmente preservado;
2. mapear a sua ligação a Leaflet, MDT, coordenadas e estado global;
3. construir um protótipo mínimo com um projeto real;
4. comparar o protótipo com os critérios do gate técnico;
5. recomendar KEEP, ADAPT ou REFACTOR para cada componente 3D relevante;
6. identificar alterações mínimas necessárias no `ProjectStore` e na UI;
7. terminar com uma decisão fundamentada antes da implementação das subfases 5B–5D.

Não deve começar uma reescrita completa do frontend antes desta validação.

## 21. Veredito

A Phase 5 fica aprovada como um percurso vertical de inteligência de terreno e planeamento guiado.

O produto deverá permitir compreender o terreno, criar uma implantação inicial, gerar elementos associados, comparar alternativas e comunicar resultados, mantendo sempre o caráter preliminar e indicativo das análises.

As decisões arquiteturais V2 permanecem válidas. Alterações ao legado são permitidas quando produzem benefício factual e são realizadas de forma controlada, documentada e testada.
