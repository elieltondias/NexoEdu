# Roteiro de demonstração — 8 a 12 minutos

1. **Problema e escopo:** microdados extensos dificultam conectar oferta, curso, instituição e território; perguntas exigem consulta rastreável. Trata-se de centro lógico de dados de 2024.
2. **Fonte e recorte:** mostrar repositório, commit e manifesto. Avisar que a demonstração usa 300 ofertas PB, não o total estadual/nacional.
3. **Modelo:** explicar diferença entre curso e oferta. Mostrar OfertaCurso → Curso → IES e OfertaCurso → Municipio → UF. A sede da IES pode estar em outra UF.
4. **Banco:** abrir o Neo4j Browser na porta 7474 (usuário `neo4j`, senha do `.env`). Filtrar pela propriedade `graph` e rodar as consultas abaixo.
5. **Interface:** Explorar dados → município João Pessoa. Mostrar 67 ofertas e 2.039 matrículas na amostra. Alterar modalidade e observar os resultados; não interpretar como censo municipal completo.
6. **GraphRAG:** Consultar → pergunta sobre UFPB/João Pessoa. Mostrar sementes, RRF, caminhos de dois saltos, PageRank e fontes. Explicar que o grafo visual é limitado e os totais usam consulta separada.
7. **Text-to-Graph:** importar `data/exemplo_documento.txt`, buscar o conteúdo e mostrar Documento → Trecho → Município/IES. A relação extraída é menção, sem inventar “oferece curso”. Se houver LLM, ativar a opção de NER/RE e comparar os vínculos (`metodo=llm`) com os do dicionário.
8. **LLM, se configurado:** mostrar os filtros produzidos, as citações, a ausência de evidência para uma pergunta fora do escopo e o **Cypher gerado no sandbox** (aba de rastreabilidade). Se não estiver configurado, explicar honestamente o modo determinístico.
9. **Algoritmos:** em Explorar dados → Algoritmos de grafo, executar o Louvain (comunidades coloridas no grafo) e um menor caminho entre duas entidades.
10. **Avaliação e limites:** mostrar testes (34), comparar lexical/vetor/híbrido, informar que Recall de entidade não mede alucinação. Expor as limitações e os experimentos pendentes.

## Consultas para o Browser

```cypher
MATCH p=(o:OfertaCurso)-[:OFERTA_DE]->(c:Curso)-[:OFERTADO_POR]->(i:IES)
WHERE o.graph='ensino_2024_amostra'
RETURN p LIMIT 15
```

```cypher
SHOW INDEXES YIELD name, type, state RETURN name, type, state
```

```cypher
SHOW CONSTRAINTS YIELD name, type RETURN name, type
```

```cypher
MATCH (o:OfertaCurso)-[:LOCALIZADA_EM]->(m:Municipio)
WHERE o.graph='ensino_2024_amostra' AND m.name_norm='joao pessoa'
RETURN count(o) AS ofertas, sum(o.QT_MAT) AS matriculas
```

## Perguntas que o grupo deve saber responder

- Por que não somar sobre cursos depois de expandir um caminho com várias classificações?
- Por que a constraint UNIQUE composta `(id, graph)` difere de apenas usar MERGE?
- Por que o índice vetorial é por grafo lógico e não global?
- Por que não comparar diretamente o score full-text com o score vetorial?
- O que impede o Cypher gerado pelo LLM de escrever no banco?
- Como o fallback NetworkX do Louvain difere do GDS?
- Por que cursos com o mesmo nome não são fundidos?
- Quais dados o LLM recebe e como as citações podem falhar?
- Por que a amostra não permite estimar o total da Paraíba?
- O que o PageRank do subgrafo realmente significa?
- O que mudaria para trabalhar com mais anos, novos documentos e usuários simultâneos?
