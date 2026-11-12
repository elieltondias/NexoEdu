# Mapeamento do enunciado

O enunciado especifica Neo4j. Esta entrega usa **Neo4j 5.26 Community** (Docker) com o driver oficial `neo4j` 5.28.8, conforme o enunciado original.

| Requisito do enunciado | Implementação / evidência | Observação |
|---|---|---|
| Domínio e dataset | Censo Superior 2024; 300 ofertas PB para execução inicial; importador da base completa (`lpg/`) | Amostra não estima população |
| Modelo LPG | Preservação dos rótulos e relações do repositório, mais Entity/Documento/Trecho; partição lógica pela propriedade `graph` | docs/ARQUITETURA.md |
| Constraints e índices | Unicidade composta `(id, graph)`, índices de propriedade (`id`, `name_norm`), full-text e vetorial **por grafo lógico** | `src/store.py`; constraints de existência exigem Enterprise, obrigatoriedade é garantida na camada de ingestão |
| Text-to-Graph NER/RE | NER por dicionário com relação `MENCIONA` (página/fonte) e **NER/RE opcional via LLM** (`SE_RELACIONA_COM` com `metodo=llm`) | Só vínculos resolvidos exatamente no catálogo; nada inventado por coocorrência |
| Entity resolution | ID canônico da fonte; normalização de alias; ambiguidades não vinculadas | Testes de nomes iguais e acentos |
| Busca híbrida | Full-text + embeddings multilíngues + RRF | Hash opcional é apenas baseline lexical |
| Cypher gerado por LLM | `LLM.cypher` gera a consulta com validação em **sandbox** (uma instrução, `RETURN` obrigatório, bloqueio de escrita, procedures só `db.`, `LIMIT 100`) e execução em transação `READ` imposta pelo servidor | Diferente da versão anterior (só filtros JSON); agora há geração livre restrita e verificável |
| Dois ou mais saltos | Caminhos de até dois saltos; oferta → curso → IES | Caminhos efetivamente usados são exibidos |
| Algoritmo de grafo | **Louvain** (GDS com fallback determinístico em NetworkX) gravando `community`; **menor caminho** (`shortestPath`); PageRank do subgrafo na ordenação/visualização | Cores por comunidade na UI |
| LLM com grounding | Contexto de caminhos, trechos e agregações; citações verificadas sintaticamente | Requer provedor configurado; veracidade ainda exige avaliação |
| Interface funcional | Streamlit com consulta, importação, exploração, algoritmos e documentação | Acesso local na 8501 |
| Grafo interativo | PyVis com JS incluído, zoom, arraste, fontes no hover, cores por comunidade | Renderiza somente o contexto recuperado |
| Rastreabilidade | IDs, fonte, página, consultas (incluindo a gerada pelo LLM), parâmetros, filtros e JSON exportável | Cobertura não é probabilidade |
| Testes automatizados | 34 testes: domínio, integração com Neo4j real e UI com AppTest do Streamlit | `tests/`; CI no GitHub Actions |
| Integração contínua | `.github/workflows/ci.yml`: Python 3.12, serviço Neo4j, LFS seletivo, unidade + integração + UI | |
| Código completo e README | Instruções Windows/Docker/Python no README | Grupo deve criar seu repositório e conceder acesso ao docente |
| Artigo técnico e defesa | `docs/ARTIGO.md` (estrutura SBC/IEEE) e roteiro em `docs/DEFESA.md` | Revisar autores, template oficial e resultados finais antes da entrega |
| Especificação original do projeto | `Projeto Final_ GraphRAG e KAG em Ciência da Computação.docx` versionada na raiz do repositório | |

Não há alegação de “nível de produção”. Para publicar seria necessário acrescentar autenticação, isolamento de usuários, backups testados, limites operacionais e validação de segurança/infraestrutura apropriados ao ambiente escolhido.
