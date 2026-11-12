import json
import re
from dataclasses import dataclass, asdict
import networkx as nx
from src.embeddings import Embedder, normalize, tokens
from src.store import identifier

@dataclass
class Filters:
    uf: str = ''
    municipio: str = ''
    curso: str = ''
    ies: str = ''
    modalidade: int = 0

BASE = '''MATCH (o:OfertaCurso)-[:OFERTA_DE]->(c:Curso)
MATCH (o)-[:OFERTADA_POR]->(i:IES)
OPTIONAL MATCH (o)-[:LOCALIZADA_EM]->(m:Municipio)-[:PERTENCE_A_UF]->(u:UF)
WITH o,c,i,m,u
WHERE o.graph=$graph
AND ($uf='' OR u.SG_UF=$uf)
AND ($municipio='' OR m.name_norm CONTAINS $municipio)
AND ($curso='' OR c.name_norm CONTAINS $curso)
AND ($ies='' OR i.name_norm CONTAINS $ies OR toLower(i.SG_IES)=$ies)
AND ($modalidade=0 OR o.TP_MODALIDADE_ENSINO=$modalidade)
'''

DETAIL = BASE + '''RETURN o.id AS oferta_id,c.name AS curso,i.name AS ies,
m.name AS municipio,u.SG_UF AS uf,o.TP_MODALIDADE_ENSINO AS modalidade,
o.QT_MAT AS matriculas,o.QT_ING AS ingressantes,o.QT_CONC AS concluintes,
o.source_file AS source_file ORDER BY matriculas DESC,oferta_id LIMIT 100'''
TOTAL = BASE + '''RETURN count(DISTINCT o) AS ofertas,count(DISTINCT c) AS cursos,
count(DISTINCT i) AS instituicoes,sum(coalesce(o.QT_MAT,0)) AS matriculas,
sum(coalesce(o.QT_ING,0)) AS ingressantes,sum(coalesce(o.QT_CONC,0)) AS concluintes'''

# Neo4j: score do índice vetorial é similaridade de cosseno mapeada para [0,1]
# (score = (1 + cosseno)/2 com quantização desligada), maior é melhor.
# Índices fulltext/vetoriais são POR GRAFO LÓGICO (rótulo = nome do grafo), para que
# o top-k aproximado não concorra com nós de outras partições.
def vector_query(graph):
    graph = identifier(graph)
    return (f"CALL db.index.vector.queryNodes('entity_embedding_{graph}',$k,$vector) YIELD node,score "
            f"WHERE node.graph=$graph RETURN node.id AS id,node.name AS name,score ORDER BY score DESC")

def lexical_query(graph):
    graph = identifier(graph)
    return (f"CALL db.index.fulltext.queryNodes('entity_search_{graph}',$text) YIELD node,score "
            f"WHERE node.graph=$graph RETURN node.id AS id,node.name AS name,score ORDER BY score DESC LIMIT 12")

EXACT = "MATCH (n:Entity {name_norm:$name, graph:$graph}) RETURN n.id AS id,n.name AS name ORDER BY n.id LIMIT 12"
PATHS = '''MATCH p=(a:Entity {id:$id, graph:$graph})-[*1..2]-(b:Entity)
WHERE a.id<>b.id RETURN p LIMIT 60'''
OFFER_PATH = '''MATCH p=(o:OfertaCurso {id:$id, graph:$graph})-[:OFERTA_DE]->(c:Curso)-[:OFERTADO_POR]->(i:IES)
RETURN p LIMIT 1'''


def rrf(rankings, k=60):
    scores = {}
    for rows in rankings:
        for rank, row in enumerate(rows,1):
            scores[row['id']] = scores.get(row['id'],0) + 1/(k+rank)
    return sorted(scores, key=lambda i:(-scores[i],i))

def filter_params(filters):
    p = asdict(filters)
    p['uf'] = p['uf'].strip().upper()
    for key in ['municipio','curso','ies']:
        p[key] = normalize(p[key].strip())
    if p['uf'] and not re.fullmatch('[A-Z]{2}',p['uf']):
        raise ValueError('UF deve ter duas letras.')
    if p['modalidade'] not in {0,1,2}:
        raise ValueError('Modalidade inválida.')
    return p

def graph_context(paths):
    """Constroi o subgrafo de contexto a partir dos caminhos Neo4j recuperados."""
    nodes = {}
    edges = {}
    records = []
    seen = set()
    for record in paths:
        path = record['p']
        path_nodes = list(path.nodes)
        path_rels = list(path.relationships)
        for n in path_nodes:
            props = dict(n)
            nodes[n.element_id] = {'id':n.element_id,'key':props.get('id',''),'name':props.get('name',''),
                                   'kind':props.get('kind',''),'source':props.get('source_file',''),
                                   'pagerank':0.0,'community':props.get('community'),
                                   'importance':props.get('pagerank')}
        parts = [dict(path_nodes[0]).get('name','?')]
        previous = path_nodes[0]
        for rel, node in zip(path_rels, path_nodes[1:]):
            props = dict(node)
            edges[rel.element_id] = {'id':rel.element_id,'source':rel.start_node.element_id,
                                     'target':rel.end_node.element_id,'type':rel.type}
            direction = '→' if rel.start_node.element_id == previous.element_id else '←'
            parts.extend([f'{direction} {rel.type}',props.get('name','?')])
            previous = node
        text = ' '.join(parts)
        if text in seen:
            continue
        seen.add(text)
        records.append({'path':text,'node_ids':[n.element_id for n in path_nodes],
            'snippets':[{'source':props.get('source_file',''),'page':props.get('page',1),'text':props['text']}
                        for props in (dict(n) for n in path_nodes) if props.get('text')]})
    graph = nx.DiGraph()
    for n in nodes.values():
        graph.add_node(n['id'])
    for e in edges.values():
        graph.add_edge(e['source'],e['target'])
    ranks = nx.pagerank(graph) if graph else {}
    by_id = {n['id']:n for n in nodes.values()}
    for n in nodes.values():
        n['pagerank'] = float(ranks.get(n['id'],0) or 0)
    records.sort(key=lambda p:-sum((by_id[i].get('importance') or by_id[i]['pagerank'] or 0)
                                   for i in p['node_ids']))
    return {'nodes':list(nodes.values()),'edges':list(edges.values()),
            'paths':[p['path'] for p in records],'path_records':records}

def structured(store, filters):
    params = filter_params(filters)
    rows = store.query(DETAIL,params)
    totals = {k:int(v or 0) for k,v in store.query(TOTAL,params)[0].items()}
    return {'rows':rows,'totals':totals,'filters':params}

def retrieve(store, question, filters=None, mode='hybrid'):
    if len(question.strip()) < 3 or len(question)>2000:
        raise ValueError('Escreva uma pergunta entre 3 e 2.000 caracteres.')
    metadata = store.metadata()
    if metadata.get('status') != 'pronto':
        raise ValueError('Importe uma base e aguarde a conclusão antes de consultar.')
    embedder = Embedder(store.settings.embedding,store.settings.model)
    if metadata.get('embedding_model') != embedder.identity:
        raise ValueError('O modelo configurado difere do usado na importação.')
    store.trace = []
    terms = tokens(question)[:20]
    lexical = store.query(lexical_query(store.settings.graph),{'text':' | '.join(terms)}) if terms and mode != 'vector' else []
    vector = store.query(vector_query(store.settings.graph),{'vector':embedder.encode([question])[0],'k':12}) if mode != 'lexical' else []
    exact = store.query(EXACT,{'name':normalize(question.strip())}) if mode != 'vector' else []
    anchors = [r['id'] for r in exact]
    seeds = list(dict.fromkeys(anchors + rrf([lexical,vector])))[:4]
    paths = []
    for seed in seeds:
        paths.extend(store.query(PATHS,{'id':seed}))
    facts = structured(store,filters) if filters is not None else None
    if facts:
        for row in facts['rows'][:8]:
            paths.extend(store.query(OFFER_PATH,{'id':row['oferta_id']}))
    context = graph_context(paths)
    evidence_ids = {n['key'] for n in context['nodes']}
    cited = [{'id':f'E{i+1}',**p} for i,p in enumerate(context['path_records'])]
    coverage = 'suficiente para os filtros' if facts and facts['totals']['ofertas'] else ('exploratória' if cited else 'insuficiente')
    return {'question':question,'scope':metadata.get('scope'),'year':metadata.get('year'),
            'mode':mode,'embedding':embedder.identity,'seeds':seeds,'graph':context,
            'evidence':cited,'facts':facts,'coverage':coverage,'consulted_node_ids':sorted(evidence_ids),
            'confidence_note':'Cobertura das evidências; não é probabilidade de a resposta estar correta.',
            'trace':store.trace.copy()}

def deterministic_answer(result):
    scope = 'Amostra parcial de 2024' if result['scope']=='amostra' else 'Base carregada de 2024'
    facts = result['facts']
    if facts is not None:
        t = facts['totals']
        if not t['ofertas']:
            return f'{scope}: nenhuma oferta encontrada para os filtros informados. Isso não prova ausência na população.'
        return (f"{scope}. Para os filtros exibidos, foram encontradas {t['ofertas']:,} ofertas, "
                f"{t['cursos']:,} cursos distintos e {t['instituicoes']:,} instituições. "
                f"As somas dos registros são {t['matriculas']:,} matrículas, {t['ingressantes']:,} ingressantes "
                f"e {t['concluintes']:,} concluintes. Fonte: consulta Cypher de agregação e tabela de ofertas abaixo. "
                'As quantidades se referem ao recorte carregado; não são uma estimativa nacional.').replace(',','.')
    if not result['evidence']:
        return 'Não há evidências suficientes na base carregada para responder.'
    lines = [f'{scope}. Relações recuperadas para explorar a pergunta:']
    lines.extend(f"[{e['id']}] {e['path']}" for e in result['evidence'][:8])
    lines.append('A busca recupera relações próximas; sem um modelo de linguagem, esta lista não interpreta a pergunta. Use os filtros para calcular números exatos do recorte.')
    return '\n\n'.join(lines)
