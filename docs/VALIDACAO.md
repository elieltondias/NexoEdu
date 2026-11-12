# Validação executada

Data: 6 de novembro de 2026. Ambiente Linux com Docker 29.9.3; imagem do projeto (Python 3.12) e `neo4j:5.26-community` com APOC e Graph Data Science 2.13.14, iniciados pelo Docker Compose deste repositório.

## Testes operacionais

**34 testes passaram** na última execução completa (`RUN_INTEGRATION=1`), sem falhas nem skips:

| Arquivo | Testes | Escopo |
|---|---:|---|
| tests/test_core.py | 11 | domínio: tipagem, identificadores, normalização, RRF, filtros, chunking, Louvain NetworkX |
| tests/test_llm.py | 7 | plano de filtros, citações, sandbox de Cypher, parse do NER/RE |
| tests/test_integration.py | 11 | Neo4j real: contagens, híbrida/multi-hop, injeção, constraints, partição, documentos, embeddings vetoriais, Louvain/menor caminho, sandbox somente leitura, NER/RE com LLM falso |
| tests/test_app.py | 5 | UI com AppTest do Streamlit |

Saída detalhada (lista dos 34 testes): `TESTES_EXECUTADOS.txt`. O mesmo conjunto roda no GitHub Actions (`.github/workflows/ci.yml`) a cada push/PR; o workflow será executado no primeiro push para o remoto.

Cobertura exercitada: IDs e tipos, booleanos inválidos, identificadores (anti-injeção), normalização, hashing, nomes ambíguos, fronteiras de palavra, RRF, filtros parametrizados, preservação de texto em trechos, contagens reais, reimportação idempotente, travessia de dois saltos, PageRank, procedência, tentativas de injeção, unicidade composta `(id, graph)`, isolamento entre partições lógicas, ordenação por similaridade de cosseno exata, menções documentais, incompatibilidade de escopo, sandbox de Cypher (leitura passa; escrita, DDL e multi-instrução bloqueados, inclusive pela transação `READ` do servidor), Louvain (cobertura de todos os nós, determinismo, isolamento), menor caminho, extração NER/RE com LLM falso e as cinco telas da interface.

A amostra importou 970 nós e 3.101 relações. A reimportação preservou essas contagens. Foram confirmadas 300 ofertas, 270 cursos e 50 instituições. João Pessoa retornou 67 ofertas e soma de 2.039 matrículas.

## Interface (AppTest)

O AppTest do Streamlit carregou Consultar, Explorar dados, Importar e Sobre o projeto sem exceções. A página Explorar aplicou o filtro de João Pessoa e retornou 67 ofertas/2.039 matrículas; a página Consultar submeteu uma pergunta, exibiu as métricas esperadas e registrou no trace as consultas `db.index.vector.queryNodes` e `db.index.fulltext.queryNodes`. Também foram testados o estado do botão de importação e a mensagem amigável de falha de conexão. Registro em `UI_VALIDACAO.json`.

Isso é validação automatizada do comportamento da aplicação, não uma inspeção visual em todos os navegadores/tamanhos de tela.

## Algoritmos de grafo

- **Louvain**: executado sobre a amostra com o plugin GDS (`gds.louvain`) — 970 nós, 58 comunidades gravadas em `community`; a projeção temporária é removida após o cálculo. O fallback NetworkX determinístico (mesmo resultado entre execuções) é coberto por teste unitário e é o caminho quando não há plugin/internet.
- **Menor caminho**: UFPB → João Pessoa retornou 1 salto (`SEDIADA_EM`); par sem caminho é reportado corretamente; partição permanece isolada.
- **PageRank**: calculado no subgrafo recuperado e usado para ordenar caminhos e dimensionar nós.

## Embeddings semânticos e documentos

O modelo sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 foi baixado e executado no container, produzindo vetores de 384 dimensões; a amostra do grafo de trabalho (`ensino_2024_amostra`) foi importada com o modelo real. O texto de exemplo gerou 1 documento, 1 trecho e 3 vínculos de menção, sem ambiguidades. A avaliação abaixo usou esse grafo.

O primeiro download do modelo ocorre na primeira importação semântica; depois permanece em cache (`embedding_cache`).

## Ensaio de recuperação

Foram usadas cinco consultas de entidade conhecida, descritas em `scripts/evaluate.py`, sobre o grafo importado com embeddings semânticos reais. As variantes lexical e híbrida incluem resolução de nomes exatos; a variante vector usa somente o índice vetorial para escolher sementes. Resultado médio de Recall de entidades nas quatro sementes (execução de 6 de novembro de 2026, Neo4j):

| Estratégia | Recall@4 médio | Latência mediana (s) |
|---|---:|---:|
| lexical | 1.00 | 0.2324 |
| vector | 0.80 | 0.2697 |
| hybrid | 1.00 | 0.2668 |

Os registros completos estão em `AVALIACAO_SEMANTICA.json`. O ensaio é pequeno e favorece correspondências de nomes exatos. A estratégia híbrida empatou com a lexical; não foi demonstrada superioridade geral da recuperação híbrida. Não se deve interpretar esse Recall como exatidão de respostas ou como taxa de redução de alucinações.

## Não validado nesta entrega

- Importação nacional completa: a amostra foi carregada no banco para validação; a base completa (`lpg/`) está no repositório, mas não foi importada neste ambiente (exige cerca de 16 GB de RAM conforme planejamento do README).
- Provedor LLM externo autenticado ou modelo local de linguagem: a integração (filtros, redação, Cypher em sandbox e NER/RE) é configurável, mas os testes usam respostas simuladas. Não há alegação de qualidade de geração real sem esse experimento.
- Execução do GitHub Actions no remoto: o workflow está versionado e validado estruturalmente, mas só rodará após o push.
- Publicação na internet, múltiplos usuários, capacidade máxima, tolerância a falhas e comparação estatística de alucinações.

## Antes da apresentação

Executar o Compose no computador da defesa, importar a amostra, conferir os números de controle e abrir o grafo. Se usar LLM, configurar o provedor e avaliar perguntas numéricas, multissalto e sem resposta — inclusive a geração de Cypher no sandbox. Se apresentar totais nacionais, importar e validar a base completa antes. Revisar o artigo (`ARTIGO.md`), inserir autores e adequar ao template SBC/IEEE solicitado pelo professor.
