# NexoEdu: consulta rastreável a microdados do ensino superior com grafos de conhecimento

**Artigo técnico para entrega final.** Estrutura em seções numeradas e referências no formato SBC/IEEE. Inserir autores, afiliação e referências primárias na revisão final do grupo; verificar o template oficial solicitado pelo professor antes da submissão.

## Resumo

Este trabalho apresenta um protótipo de centro lógico de microdados do ensino superior que combina um grafo de propriedades no Neo4j 5, recuperação híbrida textual e vetorial, travessia multissalto e consultas estruturadas com rastreabilidade completa. O sistema organiza entidades de instituições, cursos, ofertas e geografia do Censo da Educação Superior 2024 em grafos lógicos particionados por uma propriedade `graph`, com constraints de unicidade composta e índices full-text e vetoriais por partição. Uma amostra de 300 ofertas localizadas na Paraíba permite reprodução inicial. A interface Streamlit expõe caminhos, consultas Cypher — inclusive geradas por modelo de linguagem em ambiente de somente leitura —, algoritmos de grafo (Louvain, menor caminho e PageRank) e fontes para apoiar a inspeção humana. Respostas podem ser obtidas por agregações determinísticas ou por um modelo de linguagem configurável com citações verificadas. A validação executada cobre 34 testes automatizados (domínio, integração e interface) e um ensaio de recuperação com embeddings semânticos reais. A mensuração da redução de alucinações exige avaliação humana adicional.

**Palavras-chave:** GraphRAG; grafo de conhecimento; ensino superior; microdados; Neo4j; recuperação híbrida.

## 1. Introdução

Dados educacionais tabulares apresentam relações distribuídas entre códigos de instituição, curso, modalidade e território. Perguntas em linguagem natural podem exigir conexões entre esses elementos, enquanto um modelo de linguagem isolado não oferece garantia de aderência aos registros. A proposta é explicitar tais relações em um grafo de propriedades e tornar verificável o contexto fornecido à geração.

O objetivo é implementar e avaliar uma arquitetura de consulta com recuperação híbrida, travessia multissalto, algoritmos de grafo e procedência. O escopo compreende um dataset de 2024 por grafo lógico e consultas locais. Não se pretende inferir causalidade, desempenho acadêmico individual ou qualidade de instituições a partir de volume de matrículas.

## 2. Fundamentos

GraphRAG combina recuperação textual/vetorial com a estrutura de relações para ampliar o contexto de geração. Nesta implementação, o componente de conhecimento inclui esquema de domínio, regras de identidade, consultas parametrizadas e um ambiente de execução restrito para consultas geradas por modelo. KAG é empregado como orientação arquitetural de fundamentação em conhecimento explícito, sem alegar implementação integral de um framework externo.

A busca full-text prioriza correspondência lexical; o modelo multilíngue produz embeddings de entidades. O Reciprocal Rank Fusion (RRF) combina as posições dos rankings, evitando comparar escores de escalas diferentes. PageRank ordena localmente os caminhos recuperados; Louvain identifica comunidades sobre a partição completa; o menor caminho (BFS) materializa a ligação explícita entre duas entidades.

## 3. Materiais e métodos

### 3.1 Dataset e modelo

A fonte é o LPG publicado no repositório elieltondias/GraphRAG-KAG-Educacional (revisão registrada em FONTES.md), derivado dos microdados INEP/MEC 2024. A amostra seleciona 300 ofertas com município na Paraíba pela ordenação do hash dos IDs, preservando o fechamento das relações de saída: 970 nós e 3.101 relações. O recorte é não probabilístico e não produz estimativas populacionais.

O importador converte cabeçalhos tipados, preserva códigos como texto e aplica IDs canônicos com namespace de ano (`2024:`). Cada nó recebe a propriedade `graph`, e a unicidade é composta (`id`, `graph`), permitindo que múltiplos grafos lógicos coexistam no mesmo servidor Neo4j 5.26 Community sem se misturar. Índices de propriedade (`id`, `name_norm`) são globais; os índices full-text e vetoriais são criados por partição, usando o nome do grafo como rótulo adicional, para que a busca aproximada (top-k) não concorra com nós de outras partições. O índice vetorial usa cosseno com 384 dimensões e quantização desligada, de modo que `score = (1 + cosseno)/2`. Constraints de existência de propriedade exigem Neo4j Enterprise; a obrigatoriedade de `id`/`graph` é garantida pela camada de ingestão.

### 3.2 Recuperação e algoritmos

A recuperação prioriza entidades de nome exato, completa até quatro sementes com RRF sobre os rankings full-text e vetorial e recupera até 60 caminhos de comprimento um ou dois por semente. PageRank é calculado nesse subgrafo. Com filtros, uma consulta separada no grão `OfertaCurso` produz agregações exatas sobre todas as ofertas correspondentes — os indicadores nunca são somados a partir do conjunto limitado de caminhos visuais.

O Louvain é executado com o plugin Graph Data Science (GDS) quando disponível, com fallback determinístico em NetworkX (`seed=42`) para ambientes sem plugin ou sem internet; o resultado é gravado na propriedade `community` e usado para colorir a visualização. O menor caminho usa `shortestPath` do Cypher, restrito à partição, com limite de oito saltos.

### 3.3 Text-to-Graph (NER/RE)

PDFs textuais e TXT produzem trechos de até 1.100 caracteres e vínculos `MENCIONA`, por reconhecimento de entidades de dicionário e resolução de alias não ambíguos, com página e fonte. Opcionalmente, com consentimento do usuário, cada trecho também passa por NER/RE via modelo de linguagem: o modelo devolve JSON com entidades e relações, e somente nomes resolvidos exatamente no catálogo geram vínculos (`MENCIONA` com `metodo=llm` e `SE_RELACIONA_COM` com verbo, trecho, página e fonte). Relações com extremos desconhecidos ou ambíguos são ignoradas e contabilizadas. Não são extraídos fatos arbitrários de coocorrência.

### 3.4 Integração com LLM e sandbox de Cypher

A integração opcional com LLM cobre três caminhos: (i) converter perguntas em filtros JSON validados; (ii) redigir respostas fundamentadas em caminhos, trechos e agregações, com citações `[E1]` verificadas quanto à existência; e (iii) **gerar consultas Cypher** em ambiente restrito. O sandbox aceita uma única instrução de leitura com `RETURN` obrigatório, bloqueia operações de escrita (`CREATE`, `MERGE`, `DELETE`, `SET`, `DROP`, `LOAD CSV`, `BEGIN/COMMIT`…) e procedures fora de `db.`, impõe `LIMIT 100` e executa em transação `READ` — a garantia dura é do servidor Neo4j, que rejeita escritas mesmo que a validação seja contornada. A consulta gerada é exibida na aba de rastreabilidade.

## 4. Avaliação reproduzível

A validação operacional cobre tipagem, normalização, integridade, idempotência, unicidade composta, isolamento de partições, consultas parametrizadas, travessia, procedência, sandbox de Cypher e extração NER/RE. São **34 testes automatizados** (11 de domínio, 7 de integração LLM, 11 de integração com Neo4j real e 5 de interface com AppTest), executados em container e também no GitHub Actions a cada push. As quantidades de controle da amostra são 970 nós, 3.101 relações, 300 ofertas, 270 cursos e 50 instituições. Um recorte por João Pessoa contém 67 ofertas e soma 2.039 matrículas, sem interpretação populacional. O Louvain sobre a amostra produziu 58 comunidades; o menor caminho UFPB → João Pessoa retornou um salto (`SEDIADA_EM`).

O script `scripts/evaluate.py` compara recuperação lexical, vetorial e híbrida em cinco consultas de entidades conhecidas, sobre o grafo importado com embeddings semânticos reais (`paraphrase-multilingual-MiniLM-L12-v2`). A métrica é Recall de sementes em top-4, com latência observada:

| Estratégia | Recall@4 médio | Latência mediana (s) |
|---|---:|---:|
| lexical | 1.00 | 0.2324 |
| vector | 0.80 | 0.2697 |
| hybrid | 1.00 | 0.2668 |

Trata-se de um ensaio pequeno de recuperação, não um teste conclusivo de generalização ou alucinação; a variante híbrida empatou com a lexical. Resultados completos e limites estão em VALIDACAO.md e AVALIACAO_SEMANTICA.json.

Para avaliar grounding, o grupo deve ampliar o conjunto com perguntas multissalto, numéricas e sem resposta, definir gabaritos verificáveis e comparar: LLM sem contexto, RAG vetorial e GraphRAG/KAG. Dois avaliadores devem classificar afirmações suportadas, incorretas, ausentes e abstenções, com resolução das divergências. Não preencher percentuais antes de executar o estudo.

## 5. Discussão e limitações

A explicitação de fontes permite auditoria, mas não elimina erros de recuperação ou geração. A resolução por dicionário não cobre entidades inéditas, e o NER/RE via LLM depende da exatidão da correspondência no catálogo. A amostra exclui ofertas sem município e não representa estatisticamente o estado. O PageRank depende do recorte recuperado e não equivale à relevância de uma instituição no Brasil; as comunidades do Louvain descrevem a partição carregada, não agrupamentos nacionais.

O sandbox restringe escrita, mas a validação de citações é sintática: uma frase com citação existente pode ainda ser semanticamente incorreta. A implementação é local e acadêmica; a carga nacional completa, testes de escala e geração por provedor externo autenticado devem ser executados no ambiente final antes de qualquer alegação de desempenho em produção.

## 6. Considerações finais

O protótipo permite inspecionar dados e caminhos de conhecimento do ensino superior, combinando busca híbrida, algoritmos de grafo e cálculos estruturados sobre um banco Neo4j com partição lógica explícita. A contribuição prática é um pipeline reproduzível com rastreabilidade, ambiente de execução restrito para Cypher gerado por modelo e separação explícita entre amostra, dado carregado e resposta gerada. Trabalhos futuros incluem avaliação humana de grounding, mais anos de microdados, extração de relações documentais com validação de domínio e índices vetoriais com product quantization para escalas maiores.

## Referências

1. INEP/MEC. Microdados do Censo da Educação Superior 2024. Fonte declarada no LPG consultado.
2. Dias, Elielton. GraphRAG-KAG-Educacional. GitHub. Revisão em FONTES.md.
3. Neo4j, Inc. Neo4j Graph Database — Manual Cypher, índices, constraints e busca vetorial. https://neo4j.com/docs/ (acesso em FONTES.md).
4. Neo4j, Inc. Python Driver. https://neo4j.com/docs/api/python-driver/current/
5. Neo4j, Inc. Graph Data Science Library. https://neo4j.com/docs/graph-data-science/
6. Sentence Transformers / FastEmbed. Modelo multilíngue e documentação. URLs em FONTES.md.
7. [Inserir referência primária sobre GraphRAG após verificação pelo grupo.]
8. [Inserir referência primária sobre KAG após verificação pelo grupo.]
9. Cormack, G. V. et al. Reciprocal Rank Fusion. SIGIR 2009. [verificar e completar]
10. PageRank e Louvain — referências originais dos algoritmos. [verificar e completar]
