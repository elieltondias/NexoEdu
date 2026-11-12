# Fontes e atribuição

## Dados e modelo LPG

Repositório fornecido pelo grupo: https://github.com/elieltondias/GraphRAG-KAG-Educacional

Autor/proprietário apresentado pelo GitHub: elieltondias. Revisão utilizada: `2dadee4abf4f358b9b274e84ca08b67a15351a66`.

O repositório identifica a fonte primária como **INEP/MEC — Microdados do Censo da Educação Superior 2024**. Esta entrega usou seus CSVs LPG para gerar uma amostra; não baixou uma segunda cópia independente no portal INEP. A seleção não altera os valores dos campos dos registros retidos.

Procedimento da amostra:

1. Identificar municípios de CO_UF `25` no arquivo LPG de municípios.
2. Selecionar ofertas cuja CO_MUNICIPIO corresponda a esses municípios.
3. Ordenar os IDs elegíveis pelo SHA-256 UTF-8 do ID e reter os primeiros 300.
4. Percorrer todas as relações de saída desses nós e dos nós alcançados, até fechamento transitivo.
5. Reter apenas nós alcançados e relações com as duas extremidades retidas, preservando cabeçalhos e propriedades.

Foram encontradas 10.447 ofertas elegíveis no LPG de origem. A amostra resultou em 970 nós, 3.101 relações, 300 ofertas, 270 cursos e 50 IES. Ofertas sem município não entram nesse recorte. A fonte tem classificações e municípios das sedes em outras UFs, que permanecem por fechamento.

Os arquivos são uma amostra derivada atribuída à fonte. Nenhum script Python do repositório de terceiros foi copiado para a aplicação; o importador, a UI e a recuperação deste pacote foram escritos para esta entrega. O repositório consultado não apresentou arquivo LICENSE na raiz nessa revisão; a publicação/redistribuição posterior pelo grupo deve respeitar as condições da fonte e as regras institucionais de atribuição.

## Bibliotecas e documentação

- Neo4j (documentação da versão 5): https://neo4j.com/docs/
- Driver Python oficial: https://neo4j.com/docs/api/python-driver/current/
- Índices vetoriais: https://neo4j.com/docs/cypher-manual/current/indexes-for-vector-search/
- Índices full-text: https://neo4j.com/docs/cypher-manual/current/full-text-search/
- Constraints: https://neo4j.com/docs/cypher-manual/current/constraints/
- Graph Data Science (plugin opcional): https://neo4j.com/docs/graph-data-science/
- APOC (plugin opcional): https://neo4j.com/docs/apoc/
- Imagem Docker oficial: https://hub.docker.com/_/neo4j
- Streamlit: https://docs.streamlit.io/
- FastEmbed: https://github.com/qdrant/fastembed
- Modelo multilíngue: https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- NetworkX (PageRank e Louvain): https://networkx.org/documentation/stable/
- PyVis: https://pyvis.readthedocs.io/
- pypdf: https://pypdf.readthedocs.io/

As dependências possuem licenças próprias, não substituídas por este pacote. O grupo deve registrar a assistência de IA conforme as regras do professor e compreender/adaptar o código para a defesa.
