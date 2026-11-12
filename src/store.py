import re
import time
from neo4j import GraphDatabase, READ_ACCESS, WRITE_ACCESS
from neo4j.exceptions import Neo4jError
from src.config import Settings
from src.embeddings import DIMENSION

def identifier(value):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value):
        raise ValueError(f'Identificador inválido: {value!r}')
    return value

# Constraints e índices do modelo LPG no Neo4j 5 Community.
# Unicidade composta (id, graph): o mesmo ID pode existir em grafos lógicos
# diferentes, que são partições isoladas dentro do mesmo servidor.
# Obrigatoriedade de id/graph é garantida pela camada de ingestão (Store.upsert_nodes):
# constraints de existência de propriedade (IS NOT NULL) exigem Neo4j Enterprise.
# Índices fulltext e vetoriais são criados POR GRAFO LÓGICO: cada nó recebe também o
# rótulo com o nome do grafo, para que a busca aproximada (top-k) não concorra com nós
# de outros grafos antes do filtro de partição.
def base_ddl():
    return [
        'CREATE CONSTRAINT entity_uniq IF NOT EXISTS FOR (n:Entity) REQUIRE (n.id, n.graph) IS UNIQUE',
        'CREATE INDEX entity_id_idx IF NOT EXISTS FOR (n:Entity) ON (n.id)',
        'CREATE INDEX entity_name_norm_idx IF NOT EXISTS FOR (n:Entity) ON (n.name_norm)',
    ]

def graph_ddl(graph):
    graph = identifier(graph)
    return [
        f'CREATE FULLTEXT INDEX entity_search_{graph} IF NOT EXISTS FOR (n:{graph}) ON EACH [n.search_text]',
        f'CREATE VECTOR INDEX entity_embedding_{graph} IF NOT EXISTS FOR (n:{graph}) ON (n.embedding) OPTIONS '
        + "{indexConfig: {`vector.dimensions`: %d, `vector.similarity_function`: 'cosine', "
          "`vector.quantization.enabled`: false}}" % DIMENSION,
        # Índices globais de versões anteriores desta entrega; removidos se existirem.
        'DROP INDEX entity_search IF EXISTS',
        'DROP INDEX entity_embedding IF EXISTS',
    ]

class Store:
    """Acesso ao Neo4j: schema, escrita parametrizada e leitura com rastro de auditoria."""

    def __init__(self, settings=None, driver=None):
        self.settings = settings or Settings()
        identifier(self.settings.graph)
        self.driver = driver or GraphDatabase.driver(
            self.settings.uri,
            auth=(self.settings.user, self.settings.password or None),
            connection_timeout=5)
        self.trace = []

    def query(self, cypher, params=None, write=False, readonly=False):
        data = dict(params or {})
        data.setdefault('graph', self.settings.graph)
        mode = READ_ACCESS if readonly else WRITE_ACCESS
        with self.driver.session(database=self.settings.database, default_access_mode=mode) as session:
            rows = [dict(record) for record in session.run(cypher, data)]
        if not write:
            self.trace.append({'cypher': cypher, 'params': data})
        return rows

    def schema(self):
        for statement in base_ddl() + graph_ddl(self.settings.graph):
            try:
                self.query(statement, write=True)
            except Neo4jError as error:
                message = str(error).lower()
                if 'already exists' not in message and 'equivalent' not in message:
                    raise
        self.wait_ready()

    def wait_ready(self, timeout=120):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rows = self.query('SHOW INDEXES YIELD name, state, failureMessage '
                              'RETURN name, state, failureMessage')
            states = [str(row.get('state') or '').upper() for row in rows]
            failed = [row for row, state in zip(rows, states) if state == 'FAILED']
            if failed:
                raise RuntimeError(f'Falha ao construir índice/constraint: {failed}')
            if rows and all(state == 'ONLINE' for state in states):
                return
            time.sleep(0.3)
        raise TimeoutError('Índices/constraints ainda não estão prontos.')

    def metadata(self):
        rows = self.query('MATCH (m:Metadata {id:$id, graph:$graph}) RETURN properties(m) AS data',
                          {'id': 'dataset'})
        return rows[0]['data'] if rows else {}

    def set_metadata(self, data):
        self.query('MERGE (m:Metadata {id:$id, graph:$graph}) SET m += $data',
                   {'id': 'dataset', 'data': data}, write=True)

    def upsert_nodes(self, label, rows):
        label = identifier(label)
        graph_label = identifier(self.settings.graph)
        payload = []
        for row in rows:
            if not row.get('id') or not row.get('props'):
                raise ValueError('Nó sem id ou sem propriedades. Obrigatório para todo nó do grafo.')
            payload.append({'id': row['id'], 'graph': self.settings.graph, 'props': row['props']})
        self.query(
            f'UNWIND $rows AS row MERGE (n:Entity:{label}:{graph_label} {{id:row.id, graph:row.graph}}) '
            f'SET n += row.props', {'rows': payload}, write=True)

    def upsert_edges(self, kind, rows, props=False):
        kind = identifier(kind)
        set_props = ' SET r += row.props' if props else ''
        payload = [{**row, 'graph': self.settings.graph} for row in rows]
        result = self.query(
            'UNWIND $rows AS row '
            'MATCH (a:Entity {id:row.source, graph:row.graph}), '
            '(b:Entity {id:row.target, graph:row.graph}) '
            f'MERGE (a)-[r:{kind}]->(b){set_props} RETURN count(r) AS matched',
            {'rows': payload}, write=True)
        if result[0]['matched'] != len(rows):
            raise ValueError(f'Relações {kind} com origem/destino ausente. Importação incompleta.')
        return result[0]['matched']

    def vectors(self, rows):
        payload = [{**row, 'graph': self.settings.graph} for row in rows]
        self.query('UNWIND $rows AS row '
                   'MATCH (n:Entity {id:row.id, graph:row.graph}) '
                   'SET n.embedding = row.vector', {'rows': payload}, write=True)

    def stats(self):
        return self.query('MATCH (n:Entity) WHERE n.graph=$graph '
                          'RETURN n.kind AS tipo, count(n) AS quantidade ORDER BY quantidade DESC')

    def count_nodes(self):
        rows = self.query('MATCH (n:Entity) WHERE n.graph=$graph RETURN count(n) AS n')
        return rows[0]['n']

    def wipe(self):
        """Remove apenas o grafo lógico atual (usado pelos testes de integração)."""
        self.query('MATCH (n) WHERE n.graph=$graph DETACH DELETE n', write=True)

    def close(self):
        self.driver.close()
