from dataclasses import replace
import pytest
from src.config import Settings
from src.llm import LLM, validate_cypher


def model(monkeypatch, answer):
    instance=LLM(replace(Settings(),llm_url='http://example.invalid/v1',llm_model='test'))
    monkeypatch.setattr(instance,'call',lambda system,user:answer)
    return instance


def test_plan_accepts_only_typed_filters(monkeypatch):
    instance=model(monkeypatch,'{"uf":"PB","municipio":"João Pessoa","curso":"","ies":"","modalidade":0}')
    assert instance.plan('Cursos em João Pessoa').municipio=='João Pessoa'
    instance=model(monkeypatch,'{"query":"MATCH (n) DETACH DELETE n"}')
    with pytest.raises(ValueError):
        instance.plan('Cursos em João Pessoa')


def test_fabricated_citation_rejected(monkeypatch):
    instance=model(monkeypatch,'Uma afirmação [E999].')
    with pytest.raises(ValueError):
        instance.answer({'question':'x','scope':'amostra','year':2024,'evidence':[{'id':'E1','path':'A → B'}],'facts':None})


def test_absent_evidence_abstains_without_call(monkeypatch):
    instance=model(monkeypatch,'resposta que não deve ser usada')
    assert 'Não há evidências' in instance.answer({'question':'x','evidence':[],'facts':None})


def test_validate_cypher_allows_reads_and_appends_limit():
    query=validate_cypher('```cypher\nMATCH (n:Entity) WHERE n.graph=$graph RETURN n.id AS id\n```')
    assert query.endswith(' LIMIT 100')
    assert validate_cypher('MATCH (n) RETURN n LIMIT 5')=='MATCH (n) RETURN n LIMIT 5'


def test_validate_cypher_blocks_writes_and_multi_statement():
    invalid=['MATCH (n) DETACH DELETE n','CREATE (n:X {id:1})','MATCH (n) SET n.x=1',
             'MERGE (n:X)','MATCH (n) RETURN n; MATCH (m) RETURN m','DROP INDEX x',
             'MATCH (n)','LOAD CSV FROM "http://x" AS f RETURN f',
             'CALL apoc.cypher.run("MATCH (n) RETURN n") YIELD value RETURN value',
             'FOREACH (x IN [1] | CREATE (:X)) RETURN 1']
    for query in invalid:
        with pytest.raises(ValueError):
            validate_cypher(query)


def test_llm_cypher_rejects_write_query(monkeypatch):
    instance=model(monkeypatch,'MATCH (n) DETACH DELETE n')
    with pytest.raises(ValueError):
        instance.cypher('Quantas ofertas existem?')
    instance=model(monkeypatch,'MATCH (n:Entity) RETURN n LIMIT 5')
    assert 'LIMIT 5' in instance.cypher('x')


def test_llm_extract_parses_and_shapes(monkeypatch):
    instance=model(monkeypatch,'```json\n{"entidades":["UFPB"],"relacoes":[{"origem":"UFPB","relacao":"sediada em","destino":"João Pessoa"}]}\n```')
    data=instance.extract('A UFPB fica em João Pessoa.')
    assert data['entidades']==['UFPB'] and data['relacoes'][0]['relacao']=='sediada em'
    instance=model(monkeypatch,'{"entidades":"não é lista"}')
    with pytest.raises(ValueError):
        instance.extract('texto')
    instance=model(monkeypatch,'{"entidades":[],"relacoes":[],"injecao":"x"}')
    with pytest.raises(ValueError):
        instance.extract('texto')
