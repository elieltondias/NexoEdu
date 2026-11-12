import os
import uuid
from dataclasses import replace
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from src.config import Settings
from src.store import Store
from src.ingest import ingest_lpg

pytestmark = pytest.mark.skipif(os.getenv('RUN_INTEGRATION') != '1',
                                reason='Use RUN_INTEGRATION=1 com Neo4j ativo')
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def graph_name():
    """Grafo lógico exclusivo com a amostra importada em modo hash (sem download)."""
    name = 'app_' + uuid.uuid4().hex
    store = Store(replace(Settings(), graph=name, embedding='hash'))
    ingest_lpg(store, ROOT / 'data/sample/lpg', 'amostra', progress=lambda _: None)
    yield name
    store.wipe()
    store.close()


@pytest.fixture()
def app(monkeypatch, graph_name):
    monkeypatch.setenv('GRAPH_NAME', graph_name)
    monkeypatch.setenv('EMBEDDING_MODE', 'hash')
    at = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=60)
    at.run()
    return at


def test_app_loads_without_exception(app):
    assert not app.exception
    opcoes = list(app.radio[0].options)
    assert opcoes == ['Consultar', 'Explorar dados', 'Importar', 'Sobre o projeto']
    assert 'AMOSTRA REAL' in str(app.info[0].value)


def test_explore_page_shows_filtered_metrics(app):
    app.radio[0].set_value('Explorar dados').run()
    assert not app.exception
    # set_value e submit encadeados num único run: valor de form só persiste
    # quando aplicado junto com o clique em "Aplicar filtros".
    app.text_input('emunicipio').set_value('João Pessoa')
    [b for b in app.button if b.label == 'Aplicar filtros'][0].click().run()
    assert not app.exception
    valores = {m.label: m.value for m in app.metric}
    assert valores['Ofertas'] == '67'
    assert valores['Matrículas'] == '2.039'
    assert len(app.dataframe[0].value) == 67


def test_consultar_page_retrieves_with_traceability(app):
    app.radio[0].set_value('Consultar').run()
    assert not app.exception
    [b for b in app.button if b.label == 'Consultar conhecimento'][0].click().run()
    assert not app.exception
    valores = {m.label: m.value for m in app.metric}
    assert valores['Ofertas'] == '67'
    tracos = [c.value for c in app.code]
    assert any('db.index.vector.queryNodes' in t for t in tracos)
    assert any('db.index.fulltext.queryNodes' in t for t in tracos)
    assert any('Amostra parcial de 2024' in str(m.value) for m in app.markdown)


def test_import_page_offers_sample_reingest_when_scope_is_sample(app):
    app.radio[0].set_value('Importar').run()
    assert not app.exception
    botao = [b for b in app.button if b.label == 'Importar amostra da Paraíba'][0]
    # Escopo amostra: reimportação é permitida; com base completa, o botão bloqueia
    # a sobrescrita do grafo por uma amostra menor.
    assert not botao.disabled


def test_connection_failure_shows_friendly_error(monkeypatch, graph_name):
    monkeypatch.setenv('GRAPH_NAME', graph_name)
    monkeypatch.setenv('NEO4J_HOST', '127.0.0.1')
    monkeypatch.setenv('NEO4J_PORT', '9')
    at = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=60)
    at.run()
    assert not at.exception
    assert 'Não foi possível conectar ao Neo4j' in str(at.error[0].value)
