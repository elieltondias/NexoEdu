"""Algoritmos de grafo sobre o particionamento lógico (propriedade graph).

- Louvain: usa o plugin Graph Data Science (GDS) quando disponível e cai para
  uma implementação determinística em NetworkX quando não há plugin/internet.
  O resultado é gravado na propriedade `community` de cada nó da partição.
- Menor caminho: `shortestPath` do núcleo do Cypher, restrito à partição atual.
"""
from collections import Counter
import networkx as nx
from src.store import identifier

COMMUNITY_COLORS = ['#2563eb', '#ea580c', '#059669', '#9333ea', '#db2777',
                    '#0d9488', '#ca8a04', '#dc2626', '#4f46e5', '#0891b2']


def louvain_networkx(node_ids, edges, seed=42):
    """Comunidades de Louvain em grafo não direcionado (fallback offline).

    `seed` fixa torna o resultado reprodutível entre execuções.
    """
    graph = nx.Graph()
    graph.add_nodes_from(node_ids)
    graph.add_edges_from(edges)
    communities = nx.community.louvain_communities(graph, seed=seed)
    mapping = {}
    for index, members in enumerate(sorted(communities, key=lambda m: sorted(m))):
        for node in members:
            mapping[node] = index
    return mapping


def _gds_louvain(store, graph):
    """Louvain via GDS; lança exceção se o plugin não estiver disponível."""
    name = f'louvain_{identifier(graph)}'
    drop = 'CALL gds.graph.drop($name, true) YIELD graphName RETURN graphName'
    try:
        store.query(drop, {'name': name}, write=True)
    except Exception:
        pass
    store.query(
        'CALL gds.graph.project.cypher($name, '
        "'MATCH (n) WHERE n.graph = $graph RETURN id(n) AS id', "
        "'MATCH (a)-[r]->(b) WHERE a.graph = $graph AND b.graph = $graph "
        'RETURN id(a) AS source, id(b) AS target\', '
        '{parameters: {graph: $graph}}) YIELD graphName RETURN graphName',
        {'name': name, 'graph': graph}, write=True)
    try:
        rows = store.query(
            'CALL gds.louvain.stream($name) YIELD nodeId, communityId '
            'RETURN nodeId, communityId', {'name': name})
    finally:
        try:
            store.query(drop, {'name': name}, write=True)
        except Exception:
            pass
    return {row['nodeId']: int(row['communityId']) for row in rows}


def louvain(store):
    """Detecta comunidades na partição atual e grava a propriedade `community`."""
    graph = store.settings.graph
    nodes = store.query('MATCH (n:Entity) WHERE n.graph=$graph RETURN id(n) AS node_id, n.id AS key')
    if not nodes:
        raise ValueError('Grafo vazio: importe uma base antes de executar algoritmos.')
    node_ids = [row['node_id'] for row in nodes]
    algorithm = 'networkx.louvain'
    mapping = None
    try:
        mapping = _gds_louvain(store, graph)
        algorithm = 'gds.louvain'
    except Exception:
        mapping = None
    if mapping is None:
        edges = store.query('MATCH (a)-[r]->(b) WHERE a.graph=$graph AND b.graph=$graph '
                            'RETURN id(a) AS source, id(b) AS target')
        mapping = louvain_networkx(node_ids, [(e['source'], e['target']) for e in edges])
    next_id = max(mapping.values(), default=-1) + 1
    rows = []
    for row in nodes:
        community = mapping.get(row['node_id'])
        if community is None:  # nó sem arestas: comunidade própria
            community = next_id
            next_id += 1
        rows.append({'key': row['key'], 'community': int(community)})
    store.query('UNWIND $rows AS row MATCH (n:Entity {id:row.key, graph:$graph}) '
                'SET n.community=row.community', {'rows': rows}, write=True)
    sizes = Counter(row['community'] for row in rows)
    return {'algorithm': algorithm, 'nodes': len(rows), 'communities': len(sizes),
            'maiores': [{'comunidade': c, 'nos': n} for c, n in sizes.most_common(10)]}


def shortest_path(store, source, target):
    """Menor caminho não direcionado entre dois IDs canônicos da partição."""
    rows = store.query(
        'MATCH (a:Entity {id:$source, graph:$graph}), (b:Entity {id:$target, graph:$graph}) '
        'MATCH p=shortestPath((a)-[*1..8]-(b)) RETURN p LIMIT 1',
        {'source': source, 'target': target})
    if not rows:
        return {'found': False, 'origem': source, 'destino': target}
    path = rows[0]['p']
    nodes = list(path.nodes)
    rels = list(path.relationships)

    def label(node):
        props = dict(node)
        return props.get('name') or props.get('id') or node.element_id

    parts = [label(nodes[0])]
    previous = nodes[0]
    for rel, node in zip(rels, nodes[1:]):
        saida = rel.start_node.element_id == previous.element_id
        parts.extend([f"{'→' if saida else '←'} {rel.type}", label(node)])
        previous = node
    return {'found': True, 'origem': source, 'destino': target, 'saltos': len(rels),
            'caminho': ' '.join(parts),
            'nos': [{'id': dict(n).get('id'), 'nome': dict(n).get('name'),
                     'tipo': dict(n).get('kind')} for n in nodes]}
