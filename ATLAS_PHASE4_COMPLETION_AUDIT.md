# Atlas V2 — Phase 4 Completion Audit

**Data:** 2026-08-21  
**Fase:** 4 — Engine Expansion  
**Estado:** CONCLUÍDA  
**Especificação de referência:** `ATLAS_V2_ARCHITECTURE.md`

## 1. Objetivo

Confirmar que a expansão de motores da Phase 4 está integrada através dos contratos V2, que a interface só apresenta capacidades realmente disponíveis no backend e que o deploy público corresponde ao estado local auditado.

Esta auditoria não reabre decisões arquiteturais congeladas.

## 2. Resultado executivo

A Phase 4 está funcionalmente concluída para o âmbito factual atualmente suportado pelo código V1:

- `earthwork` permanece operacional através do adapter V2;
- `cultivable_area` integra o cálculo agrícola V1 com MDT real;
- `solar_potential` integra o motor solar V1;
- `water_context` integra o motor hídrico V1;
- o Type Registry é a fonte das análises apresentadas na interface;
- os resultados continuam persistidos por `ScenarioObject + engine`;
- o frontend V2 continua a usar exclusivamente o `ProjectStore` como fronteira com o backend;
- a versão publicada no Render corresponde ao frontend local auditado.

Não foram encontrados bloqueadores críticos. O estado local foi comparado com a publicação manual por identificador de conteúdo, o histórico foi sincronizado e a release recebeu um commit final auditado.

## 3. Matriz de motores

| Motor V2 | Objeto | Adapter | TerrainContext | Estado |
|---|---|---|---|---|
| `earthwork` | `platform` | `EarthworkAdapter` | obrigatório, lazy | PASS |
| `cultivable_area` | `crop_area` | `CultivableAreaAdapter` | obrigatório, lazy | PASS |
| `solar_potential` | `zone` | `SolarPotentialAdapter` | não requerido | PASS |
| `water_context` | `zone` | `WaterContextAdapter` | não requerido | PASS |

## 4. Type Registry publicado

O endpoint público `GET /api/v2/types` anuncia:

- `platform` → `earthwork`;
- `crop_area` → `cultivable_area`;
- `zone` → `solar_potential`, `water_context`;
- `pond` → nenhum motor V2;
- `access` → nenhum motor V2.

O frontend deixou de manter uma lista independente de motores. As ações disponíveis são agora derivadas do Registry carregado pelo `ProjectStore`.

Consequência: uma instalação nunca deve voltar a apresentar um botão para um motor que o respetivo backend não anuncia.

## 5. Agricultura

O percurso agrícola foi validado de ponta a ponta com uma geometria dentro da cobertura MDT:

1. área agrícola presente numa alternativa;
2. ação **Avaliar cultivo** apresentada;
3. pedido enviado como `engine_type = cultivable_area`;
4. adapter encontrado e executado;
5. resultado persistido e apresentado na interface;
6. ausência da mensagem `Motor não suportado`.

Resultado observado durante QA:

- área total: 2,938 ha;
- área cultivável: 0,169 ha;
- aproveitamento: 5,8%;
- estado: parcial, devido às limitações das fontes SIG externas.

Os registos temporários criados para esta validação foram removidos após o teste.

## 6. Persistência e cenários

Foram confirmados por testes automatizados:

- identidade própria de `ScenarioObject`;
- isolamento por snapshot;
- duplicação de cenário;
- atualização explícita a partir do objeto de projeto;
- preservação do snapshot após eliminação do `ProjectObject` original;
- staleness derivado através dos timestamps congelados;
- substituição do resultado mais recente por `ScenarioObject + engine`;
- múltiplos motores associados ao mesmo objeto sem colisão frontend.

## 7. Geometria, CRS e terreno

Mantêm-se inalterados:

- GeoJSON como contrato de geometria;
- WGS84 na comunicação Leaflet e transformação interna para TM06 / EPSG:3763;
- rejeição de geometria inválida;
- warning para geometria parcialmente fora da BaseParcel;
- rejeição de geometria totalmente fora;
- TerrainContext lazy e project-session scoped;
- recorte do MDT apenas para adapters que o requerem.

O teste de `earthwork` e o teste agrícola usam MDT real.

## 8. Charca e drainage

### Charca

O motor V1 de charca continua no fluxo legado.

Não foi criado um `PondAdapter` artificial porque o motor V1 requer uma barreira linear e um ponto a montante, enquanto o objeto V2 `pond` representa um polígono. Forçar a integração quebraria o contrato factual ou exigiria uma decisão de domínio ainda não tomada.

Esta situação é uma exceção consciente e segura, não uma falha da Phase 4.

### Drainage

Não existe atualmente um adapter de drenagem geométrica seguro. O motor hídrico existente fornece contexto hídrico por localização e foi integrado como `water_context`; não deve ser apresentado como cálculo de drenagem.

`drainage` permanece diferido até existir um contrato factual de input/output e um consumidor claro.

## 9. UX e compatibilidade V1

Confirmado no deploy público:

- navegação **Explorar / Proposta / Resultados**;
- painel rebatível;
- gestão contextual de área de trabalho e alternativa;
- criação progressiva de intervenções;
- resultados por intervenção;
- controlos V1 de charca, terraplanagem, agricultura e 3D preservados;
- ausência de erros ou warnings na consola durante a auditoria read-only.

O `project_store.js` publicado tem o mesmo SHA-256 do ficheiro local:

`d9790e4b668ce86ef545fee40d6a5bc7815c72e48e34e001bbcd1d81a6de0e37`

## 10. Testes executados

Suite local:

- 11 testes executados;
- 11 testes aprovados;
- 0 falhas;
- sintaxe de `project_store.js` válida;
- sintaxe do JavaScript inline válida;
- `git diff --check` sem erros.

Cobertura relevante:

- CRUD e BaseParcel imutável;
- validação e containment;
- Registry e schemas;
- Registry apenas anuncia adapters existentes;
- earthwork com MDT;
- agricultura com MDT;
- solar e água sem carregamento desnecessário do MDT;
- snapshots, provenance e staleness.

## 11. Validação do Render

Verificação read-only executada em `https://atlas-vyux.onrender.com/`:

- página principal: disponível;
- nova interface: publicada;
- `GET /api/v2/types`: disponível e coerente;
- `project_store.js`: igual ao local;
- navegação funcional sem erros de consola.

Não foram criados projetos, cenários ou resultados no Render durante esta auditoria.

## 12. Limitações conhecidas

- serviços externos V1 podem devolver resultados parciais ou indisponibilidade temporária;
- operações dependentes de MDT estão limitadas à cobertura raster instalada;
- não existe comparação visual lado a lado entre alternativas;
- não existe exportação de relatório ou backup;
- undo/redo continua diferido;
- `pond` e drainage permanecem sem adapter pelas razões factuais documentadas.

## 13. Fecho da release

Concluído:

1. repositório local sincronizado com o estado publicado;
2. commit final criado para Phase 4 + correções UX, após revisão do diff;
3. versão servida pelo Render comparada com o conteúdo do commit publicado.

Permanece opcional um smoke test de escrita no Render com um projeto QA explicitamente autorizado e removido depois. Esta verificação não bloqueia o fecho da fase porque a suite local já cobre os fluxos persistentes e a auditoria pública foi deliberadamente read-only.

## 14. Conclusão

**Veredito:** PASS, sem bloqueadores funcionais.

A expansão de motores está integrada de forma coerente com a arquitetura V2 e o bug `Motor não suportado` foi eliminado na origem. A Phase 4 e o respetivo fecho de release ficam declarados concluídos.

A arquitetura não define uma Phase 5; o progresso futuro deve ser decidido numa conferência de produto e engenharia.

