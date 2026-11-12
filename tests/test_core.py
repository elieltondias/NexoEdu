import math
import pytest
from src.embeddings import Embedder, normalize
from src.ingest import typed_row, batched
from src.documents import resolve_mentions, chunks
from src.store import identifier
from src.retrieval import Filters, filter_params, rrf


def test_types_preserve_codes_and_missing():
    assert typed_row({':ID':'x','CO_IES':'001','QT_MAT:long':'12','IN_GRATUITO:boolean':'true','x':''})=={'CO_IES':'001','QT_MAT':12,'IN_GRATUITO':True}


def test_invalid_boolean_rejected():
    with pytest.raises(ValueError):
        typed_row({'IN_X:boolean':'yes'})


def test_identifiers_block_cypher_injection():
    for value in ['Curso`) DELETE n //','A;B','']:
        with pytest.raises(ValueError):
            identifier(value)


def test_normalization_and_embedding_reproducibility():
    assert normalize('João Pessoa')=='joao pessoa'
    a,b=Embedder('hash').encode(['Matrículas na Paraíba','Matrículas na Paraíba'])
    assert a==b and len(a)==384
    assert math.isclose(sum(v*v for v in a),1)


def test_hash_is_lexical_not_semantic():
    a,b=Embedder('hash').encode(['Universidade','Universidade'])
    assert a==b


def test_entity_resolution_ambiguous_name_not_merged():
    catalog=[{'id':'1','name':'Direito'},{'id':'2','name':'Direito'},{'id':'3','name':'Universidade Federal da Paraíba','alias':'UFPB'}]
    ids,ambiguous=resolve_mentions('A UFPB e o curso de Direito.',catalog)
    assert ids==['3'] and ambiguous==['direito']


def test_entity_resolution_word_boundaries():
    assert resolve_mentions('ABCDEF',[{'id':'1','name':'ABC'}])==([],[])


def test_rrf_combines_ranks_without_raw_score_comparison():
    assert rrf([[{'id':'a','score':.1},{'id':'b','score':.9}],[{'id':'b','score':1000}]])[0]=='b'


def test_filter_values_are_parameters():
    f=filter_params(Filters(uf='pb',curso="Direito' DELETE n"))
    assert f['uf']=='PB' and f['curso']=="direito' delete n"
    with pytest.raises(ValueError):
        filter_params(Filters(uf='PB OR 1=1'))


def test_chunking_has_no_loss_or_empty_chunk():
    text='ensino superior '*1000
    result=list(chunks(text))
    assert all(0<len(c)<=1100 for c in result)
    assert ' '.join(result)==text.strip()
    assert list(batched(range(5),2))==[[0,1],[2,3],[4]]


def test_louvain_networkx_detects_separate_communities_deterministically():
    from src.algorithms import louvain_networkx
    nodes=['a','b','c','d','isolado']
    edges=[('a','b'),('c','d')]
    first=louvain_networkx(nodes,edges)
    second=louvain_networkx(nodes,edges)
    assert first==second
    assert first['a']==first['b'] and first['c']==first['d']
    assert first['a']!=first['c']
    assert first['isolado'] in set(first.values())
