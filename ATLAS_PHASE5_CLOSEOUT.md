# ATLAS V2 — Phase 5 Closeout

**Estado de desenvolvimento:** 5A–5D CONCLUÍDAS LOCALMENTE  
**Data:** 22 de agosto de 2026  
**Arquitetura:** preservada, sem exceções factuais

## Marcos concluídos

| Subfase | Resultado | Gate local |
|---|---|---|
| 5A | terreno 3D recortado ao projeto, imagem aérea/altitude, objetos e seleção 2D/3D | aprovado |
| 5B | assistente de edifício, plataforma, acesso e terraplanagem preliminar | aprovado |
| 5C | comparação explicável, cinzento por insuficiência, condicionantes e relevo | aprovado |
| 5D | imagens, PDF simples, relatório técnico a pedido e linguagem cautelosa | aprovado |

## Percurso vertical disponível

Um utilizador pode:

1. criar ou abrir um projeto e a sua BaseParcel;
2. abrir o terreno 3D;
3. criar uma alternativa;
4. usar o assistente para posicionar um edifício;
5. guardar edifício, plataforma e acesso como `ScenarioObject`;
6. obter a estimativa preliminar de terraplanagem;
7. criar ou duplicar outra alternativa;
8. comparar alternativas com razões, fontes e limitações;
9. consultar a adequação preliminar do relevo;
10. exportar imagens e relatórios.

## Gate final local

- 23 testes Python aprovados;
- sintaxe Python e JavaScript aprovada;
- `git diff --check` aprovado;
- fluxos 2D, 3D, comparação e exportação validados no browser local;
- PDF A4 renderizado e inspecionado visualmente;
- layout estreito validado;
- zero erros ou warnings na consola nos percursos finais.

## Atividades externas antes de declarar produção

O desenvolvimento planeado está concluído localmente, mas ainda não foram executados:

- publicação desta versão;
- smoke test no Render;
- teste moderado com participantes reais sem formação SIG;
- revisão jurídica, topográfica, arquitetónica, de engenharia ou licenciamento;
- commit ou push das alterações locais.

Estas atividades não devem ser declaradas como concluídas até ocorrerem de facto.

## Arquitetura

As subfases 5A–5D não alteraram os contratos congelados de persistência, identidade, staleness, geometria, CRS ou integração dos motores V1. `ProjectStore` permanece a única fronteira frontend/backend V2. Não foi introduzido um contrato artificial para a charca V1.

