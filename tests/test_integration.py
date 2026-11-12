import os
import uuid
from dataclasses import replace
from pathlib import Path
import pytest
from src.config import Settings
from src.store import Store
from src.ingest import ingest_lpg
from src.documents import ingest_document
from src.retrieval import retrieve, structured, Filters, deterministic_answer, vector_query

pytestmark=pytest.mark.skipif(os.getenv('RUN_INTEGRATION')!='1',reason='Use RUN_INTEGRATION=1 com Neo4j ativo')
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def store():
    settings=replace(Settings(),graph='teste_'+uuid.uuid4().hex,embedding='hash')
    store=Store(settings)
    ingest_lpg(store,ROOT/'data/sample/lpg','amostra',progress=lambda _:None)
    yield store
    store.wipe()
    store.close()


def test_real_counts_and_idempotency(store):
    facts=structured(store,Filters())
    assert facts['totals']['ofertas']==300
    assert facts['totals']['cursos']==270
    assert facts['totals']['instituicoes']==50
    before=store.stats()
    ingest_lpg(store,ROOT/'data/sample/lpg','amostra',progress=lambda _:None)
    assert store.stats()==before
    assert store.query('MATCH (a:Entity)-[r]->(b:Entity) WHERE a.graph=$graph RETURN count(r) AS n')[0]['n']==3101


def test_hybrid_multi_hop_and_provenance(store):
    result=retrieve(store,'Cursos em João Pessoa',Filters(municipio='João Pessoa'))
    assert result['facts']['totals']['ofertas']==67
    assert result['facts']['totals']['matriculas']==2039
    assert result['graph']['edges'] and result['evidence']
    assert any(e['path'].count('→')+e['path'].count('←')>=2 for e in result['evidence'])
    assert all(n['source'] for n in result['graph']['nodes'])
    assert all(n['pagerank']>0 for n in result['graph']['nodes'])
    assert 'Amostra' in deterministic_answer(result)
    assert any('db.index.vector.queryNodes' in q['cypher'] for q in result['trace'])
    assert any('db.index.fulltext.queryNodes' in q['cypher'] for q in result['trace'])


def test_query_injection_does_not_mutate(store):
    rows=structured(store,Filters(curso="') DETACH DELETE n //"))
    assert rows['totals']['ofertas']==0
    assert structured(store,Filters())['totals']['ofertas']==300


def test_constraints_enforced(store):
    from neo4j.exceptions import Neo4jError
    with pytest.raises(Neo4jError):
        store.query("CREATE (:Entity {id:'2024:uf_25', graph:$graph})",write=True)
    with pytest.raises(ValueError):
        store.upsert_nodes('Teste',[{'props':{'name':'sem id'}}])


def test_graph_partition_keeps_same_id_in_isolated_graph():
    from neo4j.exceptions import Neo4jError
    a=Store(replace(Settings(),graph='part_a_'+uuid.uuid4().hex,embedding='hash'))
    b=Store(replace(Settings(),graph='part_b_'+uuid.uuid4().hex,embedding='hash'))
    try:
        a.schema(); b.schema()
        row={'id':'particao:1','props':{'id':'particao:1','name':'nó','kind':'Teste'}}
        a.upsert_nodes('Teste',[row])
        b.upsert_nodes('Teste',[row])
        assert a.query("MATCH (n:Entity {id:'particao:1', graph:$graph}) RETURN count(n) AS n")[0]['n']==1
        assert b.query("MATCH (n:Entity {id:'particao:1', graph:$graph}) RETURN count(n) AS n")[0]['n']==1
        assert a.query("MATCH (n:Entity {id:'particao:1'}) RETURN count(n) AS n")[0]['n']==2
        with pytest.raises(Neo4jError):
            a.query("CREATE (:Entity {id:'particao:1', graph:$graph})",write=True)
    finally:
        a.wipe(); a.close()
        b.wipe(); b.close()


def test_documents_mentions_and_text_retrievable(store):
    content='João Pessoa é mencionado neste documento didático de teste.'.encode()
    first=ingest_document(store,'teste.txt',content)
    second=ingest_document(store,'teste.txt',content)
    assert first['sha256']==second['sha256']
    assert first['mencoes']==1
    result=retrieve(store,'documento didático João Pessoa',mode='lexical')
    assert any(e['snippets'] for e in result['evidence'])
    assert store.query('MATCH (n:Trecho) WHERE n.graph=$graph RETURN count(n) AS n')[0]['n']==1


def test_scope_or_embedding_mismatch_rejected(store):
    with pytest.raises(ValueError):
        ingest_lpg(store,ROOT/'data/sample/lpg','completa',progress=lambda _:None)


def test_vector_ranking_by_cosine_similarity():
    import time
    s=Store(replace(Settings(),graph='vetor_'+uuid.uuid4().hex,embedding='hash'))
    try:
        s.schema()
        vectors={'igual':[1.0]+[0.0]*383,'ortogonal':[0.0,1.0]+[0.0]*382,'oposto':[-1.0]+[0.0]*383}
        s.upsert_nodes('Teste',[{'id':k,'props':{'id':k,'name':k,'kind':'Teste'}} for k in vectors])
        s.vectors([{'id':k,'vector':v} for k,v in vectors.items()])
        s.wait_ready()
        rows=[]
        for _ in range(20):
            rows=s.query(vector_query(s.settings.graph),{'vector':vectors['igual'],'k':3})
            if len(rows)==3:
                break
            time.sleep(0.25)
        assert [r['id'] for r in rows]==['igual','ortogonal','oposto']
        assert rows[0]['score']==pytest.approx(1.0,abs=1e-6)
        assert rows[1]['score']==pytest.approx(0.5,abs=1e-6)
        assert rows[2]['score']==pytest.approx(0.0,abs=1e-6)
    finally:
        s.wipe()
        s.close()


def test_louvain_communities_and_shortest_path(store):
    from src.algorithms import louvain, shortest_path
    summary=louvain(store)
    assert summary['algorithm'] in {'gds.louvain','networkx.louvain'}
    assert summary['nodes']==store.count_nodes()
    assert summary['communities']>=1
    labeled=store.query('MATCH (n:Entity) WHERE n.graph=$graph AND n.community IS NOT NULL RETURN count(n) AS n')[0]['n']
    assert labeled==summary['nodes']
    edge=store.query('MATCH (a:Entity)-[r]->(b:Entity) WHERE a.graph=$graph RETURN a.id AS a, b.id AS b LIMIT 1')[0]
    path=shortest_path(store,edge['a'],edge['b'])
    assert path['found'] and path['saltos']==1 and path['nos']
    assert not shortest_path(store,'2024:ies_579','id_que_nao_existe:x')['found']
    # Partição isolada: comunidades calculadas num grafo não afetam o outro
    other=Store(replace(Settings(),graph='alg_'+uuid.uuid4().hex,embedding='hash'))
    try:
        other.schema()
        other.upsert_nodes('Teste',[{'id':'alg:1','props':{'id':'alg:1','name':'n','kind':'Teste'}}])
        before=other.query("MATCH (n:Entity {id:'alg:1', graph:$graph}) RETURN n.community AS c")[0]['c']
        assert before is None
    finally:
        other.wipe(); other.close()


def test_cypher_sandbox_runs_readonly_and_blocks_writes():
    from neo4j.exceptions import Neo4jError
    from src.llm import validate_cypher
    s=Store(replace(Settings(),graph='sandbox_'+uuid.uuid4().hex,embedding='hash'))
    try:
        s.schema()
        s.upsert_nodes('Teste',[{'id':'sb:1','props':{'id':'sb:1','name':'n','kind':'Teste'}}])
        query=validate_cypher('MATCH (n:Entity) WHERE n.graph=$graph RETURN n.id AS id')
        rows=s.query(query,readonly=True)
        assert rows==[{'id':'sb:1'}]
        with pytest.raises(Neo4jError):
            s.query("MATCH (n:Entity {id:'sb:1', graph:$graph}) DELETE n",readonly=True)
        assert s.count_nodes()==1
    finally:
        s.wipe(); s.close()


def test_document_with_llm_ner_and_relation_extraction(store):
    class FakeLLM:
        enabled=True
        def extract(self,chunk):
            return {'entidades':['UFPB','João Pessoa','Entidade Que Não Existe'],
                    'relacoes':[{'origem':'UFPB','relacao':'sediada em','destino':'João Pessoa'},
                                {'origem':'Fantasma','relacao':'x','destino':'João Pessoa'}]}
    result=ingest_document(store,'ner_llm.txt','A UFPB fica em João Pessoa.'.encode(),llm=FakeLLM())
    assert result['chunks_com_llm']==1 and result['erros_llm']==0
    assert result['mencoes_llm']==2
    assert result['relacoes_llm']==1 and result['relacoes_ignoradas']==1
    rel=store.query('MATCH (a:Entity)-[r:SE_RELACIONA_COM]->(b:Entity) WHERE a.graph=$graph '
                    'RETURN a.id AS a,b.id AS b,r.relacao AS relacao,r.metodo AS metodo,r.trecho AS trecho')
    assert len(rel)==1
    assert rel[0]['relacao']=='sediada em' and rel[0]['metodo']=='llm'
    assert rel[0]['a']=='2024:ies_579' and rel[0]['b']=='2024:municipio_2507507'
    assert store.query('MATCH (a:Entity {id:\'2024:ies_579\'})<-[r:MENCIONA]-() '
                       'WHERE a.graph=$graph AND r.metodo=\'llm\' RETURN count(r) AS n')[0]['n']>=1
