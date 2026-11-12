import json
from dataclasses import asdict
from pathlib import Path
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from src.config import Settings
from src.store import Store
from src.ingest import ingest_lpg
from src.documents import ingest_document
from src.retrieval import Filters, retrieve, deterministic_answer, structured
from src.llm import LLM
from src.algorithms import louvain, shortest_path
from src.visualization import render_graph

st.set_page_config(page_title='NexoEdu · Microdados do ensino superior',page_icon='◈',layout='wide')
st.markdown('''<style>
.stApp{background:#f5f7fa;color:#172033}h1,h2,h3{font-weight:550!important;letter-spacing:-.035em}
[data-testid="stSidebar"]{background:#fff;border-right:1px solid #e5e9ef}
.block-container{padding-top:2rem;max-width:1440px}
[data-testid="stMetric"]{background:white;padding:18px;border:1px solid #e5e9ef;border-radius:12px}
.stButton>button{border-radius:8px}div[data-testid="stCaptionContainer"]{color:#64748b}
</style>''',unsafe_allow_html=True)
settings = Settings()
llm = LLM(settings)
with st.sidebar:
    st.title('◈ NexoEdu')
    st.caption('CENTRO DE MICRODADOS\n\nEnsino superior · GraphRAG / KAG')
    st.divider()
    page = st.radio('Área de trabalho',['Consultar','Explorar dados','Importar','Sobre o projeto'],label_visibility='collapsed')
    st.divider()
    st.caption(f'Banco: Neo4j 5\n\nGrafo lógico: {settings.graph}\n\nEmbeddings: {settings.embedding}')
    st.caption('LLM conectado por configuração' if llm.enabled else 'Modo sem LLM · evidências e cálculos')

st.title(page if page!='Consultar' else 'Conhecimento que conecta a educação')
st.caption('Censo da Educação Superior 2024 · instituições, cursos, ofertas e território')
try:
    store_key = (settings.uri, settings.user, settings.password, settings.database, settings.graph)
    if st.session_state.get('store_key') != store_key:
        st.session_state['store'] = Store(settings)
        st.session_state['store_key'] = store_key
    store = st.session_state['store']
    meta = store.metadata()
except Exception as error:
    st.error('Não foi possível conectar ao Neo4j. Inicie o servidor com docker compose up -d neo4j.')
    with st.expander('Detalhes da conexão'):
        st.code(str(error))
    st.stop()

if st.session_state.get('active_graph') != settings.graph:
    st.session_state.pop('result',None)
    st.session_state.pop('explore',None)
    st.session_state['active_graph']=settings.graph
ready = meta.get('status')=='pronto'
if meta.get('scope')=='amostra':
    st.info('AMOSTRA REAL · 300 ofertas localizadas na Paraíba, com entidades relacionadas. Os resultados não representam totais da Paraíba nem do Brasil. Sedes das IES podem estar em outros estados.')
elif ready:
    st.info('BASE COMPLETA IMPORTADA · resultados do recorte de 2024 carregado neste grafo.')
else:
    st.warning('Base ainda não está pronta. Acesse Importar e carregue a amostra para começar.')


def filters_ui(prefix):
    a,b,c = st.columns([1,2,2])
    uf = a.text_input('UF da oferta',value='',max_chars=2,key=prefix+'uf',placeholder='PB')
    municipio = b.text_input('Município da oferta',value='João Pessoa' if prefix=='q' else '',key=prefix+'municipio',placeholder='João Pessoa')
    curso = c.text_input('Nome do curso',key=prefix+'curso',placeholder='Computação')
    d,e = st.columns([2,1])
    ies = d.text_input('Instituição ou sigla',key=prefix+'ies',placeholder='UFPB')
    modalidade = e.selectbox('Modalidade',['Todas','Presencial','A distância'],key=prefix+'modalidade')
    return Filters(uf,municipio,curso,ies,['Todas','Presencial','A distância'].index(modalidade))


def metrics(totals):
    cols=st.columns(4)
    for col,key,label in zip(cols,['ofertas','instituicoes','matriculas','concluintes'],['Ofertas','Instituições','Matrículas','Concluintes']):
        col.metric(label,f"{int(totals[key]):,}".replace(',','.'))

if page=='Importar':
    st.subheader('Um ponto de partida reproduzível')
    st.write('A amostra incluída usa registros reais do repositório informado. A importação pode ser repetida sem duplicar IDs e relações.')
    if settings.embedding=='semantic':
        st.caption('Na primeira importação, o modelo multilíngue será baixado. É necessário acesso à internet. Depois, o modelo permanece no cache.')
    if st.button('Importar amostra da Paraíba',type='primary',disabled=bool(meta and meta.get('scope')!='amostra')):
        try:
            with st.status('Preparando a base...',expanded=True) as status:
                message=st.empty()
                result=ingest_lpg(store,Path(__file__).parent/'data/sample/lpg','amostra',progress=message.write)
                status.update(label='Amostra importada',state='complete',expanded=False)
            st.success('Importação concluída. Abra Consultar ou Explorar dados.')
            st.json(result)
        except Exception as error:
            st.error(f'Falha na importação: {error}')
    with st.expander('Usar o repositório completo'):
        st.write('Execute no terminal, dentro da pasta do projeto:')
        st.code('python -m src.cli ingest --path lpg --scope completa --graph ensino_2024_completo',language='bash')
        st.write('Depois configure GRAPH_NAME=ensino_2024_completo no .env e reinicie a aplicação. No Docker, veja os comandos equivalentes no README. A base completa exige mais memória e tempo.')
    st.divider()
    st.subheader('Documentos complementares')
    st.write('Extração por dicionário de entidades já cadastradas: documento → trecho → entidade mencionada. Menções ambíguas ficam sem vínculo automático.')
    upload=st.file_uploader('PDF com texto ou TXT em UTF-8',type=['pdf','txt'])
    consent=st.checkbox('Autorizo enviar trechos deste documento ao provedor configurado quando usar o LLM.') if llm.enabled else True
    use_llm_ner=st.checkbox('Usar LLM para NER/RE (extrai entidades e relações além do dicionário)',value=False,disabled=not llm.enabled)
    if st.button('Extrair entidades e relações',disabled=not ready or upload is None or not consent):
        try:
            with st.spinner('Extraindo e indexando os trechos...'):
                result=ingest_document(store,upload.name,upload.getvalue(),llm=llm if use_llm_ner else None)
            st.success('Documento processado.')
            st.json(result)
        except Exception as error:
            st.error(str(error))
    if ready:
        with st.expander('Índices, restrições e metadados'):
            st.json(meta)
            st.dataframe(pd.DataFrame(store.query('SHOW INDEXES')).astype(str),hide_index=True)
            st.dataframe(pd.DataFrame(store.query('SHOW CONSTRAINTS')).astype(str),hide_index=True)

elif page=='Consultar':
    st.write('Faça uma pergunta, acompanhe as evidências e explore o caminho até a fonte.')
    with st.form('question'):
        question=st.text_area('O que você quer investigar?',value='Quais instituições oferecem cursos em João Pessoa?',height=95)
        use_filters=st.checkbox('Calcular indicadores com os filtros abaixo',value=True)
        filters=filters_ui('q')
        a,b=st.columns(2)
        mode=a.selectbox('Estratégia de recuperação',['hybrid','lexical','vector'],format_func=lambda v:{'hybrid':'Híbrida · texto + vetor + grafo','lexical':'Texto + grafo','vector':'Vetor + grafo'}[v])
        use_llm=b.checkbox('Redigir resposta com LLM',value=False,disabled=not llm.enabled)
        auto_plan=st.checkbox('Interpretar a pergunta em filtros com LLM (substitui os filtros manuais)',disabled=not llm.enabled)
        gen_cypher=st.checkbox('Gerar consulta Cypher com LLM (sandbox de somente leitura)',disabled=not llm.enabled)
        submitted=st.form_submit_button('Consultar conhecimento',type='primary',disabled=not ready)
    if not llm.enabled:
        st.caption('Sem LLM, a pergunta orienta a busca de relações. Para números, preencha os filtros: eles determinam o cálculo, independentemente da pergunta.')
    if submitted:
        try:
            with st.spinner('Recuperando e conectando evidências...'):
                active=llm.plan(question) if auto_plan else (filters if use_filters else None)
                result=retrieve(store,question,active,mode)
                answer=deterministic_answer(result)
                if use_llm:
                    try:
                        answer=llm.answer(result)
                        result['generation']='llm'
                    except Exception as error:
                        st.warning(f'O LLM não concluiu uma resposta válida. Exibindo evidências e cálculos. Detalhe: {error}')
                result['answer']=answer
                if gen_cypher:
                    try:
                        consulta=llm.cypher(question,meta)
                        linhas=store.query(consulta,readonly=True)
                        result['cypher_llm']={'consulta':consulta,'linhas':linhas[:100]}
                    except Exception as error:
                        st.warning(f'Cypher gerado recusado pelo sandbox ou execução falhou. Detalhe: {error}')
                st.session_state['result']=result
        except Exception as error:
            st.error(str(error))
    result=st.session_state.get('result')
    if result:
        st.divider()
        st.subheader('Resposta e evidências')
        if result['facts']:
            st.caption('Filtros efetivamente executados: '+json.dumps(result['facts']['filters'],ensure_ascii=False))
            metrics(result['facts']['totals'])
        st.markdown(result['answer'])
        st.caption(f"Cobertura: {result['coverage']}. {result['confidence_note']}")
        tabs=st.tabs(['Grafo de contexto','Fontes e caminhos','Ofertas recuperadas','Cypher e rastreabilidade'])
        with tabs[0]:
            if result['graph']['nodes']:
                components.html(render_graph(result['graph']),height=590,scrolling=False)
                st.caption('Arraste os nós, use o zoom e passe o mouse para ver a fonte. O tamanho do nó usa PageRank calculado apenas no subgrafo recuperado. Cores por comunidade quando o Louvain já foi executado em Explorar dados.')
            else:
                st.info('Nenhum caminho encontrado.')
        with tabs[1]:
            for evidence in result['evidence']:
                st.write(f"[{evidence['id']}] {evidence['path']}")
                for snippet in evidence.get('snippets',[]):
                    st.caption(f"{snippet['source']} · página {snippet['page']}: {snippet['text']}")
        with tabs[2]:
            rows=result['facts']['rows'] if result['facts'] else []
            st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
            st.caption('Até 100 linhas, ordenadas por matrículas. Os indicadores usam todas as ofertas que correspondem aos filtros.')
            if rows:
                st.download_button('Exportar tabela CSV',pd.DataFrame(rows).to_csv(index=False,sep=';').encode('utf-8-sig'),'ofertas_recuperadas.csv','text/csv')
        with tabs[3]:
            generated=result.get('cypher_llm')
            if generated:
                st.markdown('**Cypher gerado pelo LLM** · sandbox: uma instrução, só leitura, transação `READ` imposta pelo servidor, limite de 100 linhas.')
                st.code(generated['consulta'],language='cypher')
                if generated['linhas']:
                    st.dataframe(pd.DataFrame(generated['linhas']),hide_index=True,width='stretch')
                else:
                    st.info('A consulta não retornou linhas.')
            st.json({'sementes':result['seeds'],'nos_consultados':result['consulted_node_ids'],'embedding':result['embedding']})
            for entry in result['trace']:
                st.code(entry['cypher'],language='cypher')
                params={k:(f'vetor de {len(v)} dimensões' if k=='vector' else v) for k,v in entry['params'].items()}
                st.json(params)
        st.download_button('Baixar resposta e auditoria JSON',json.dumps(result,ensure_ascii=False,indent=2),'consulta_nexoedu.json','application/json')

elif page=='Explorar dados':
    if not ready:
        st.stop()
    st.subheader('Explore o recorte carregado')
    with st.form('explore_form'):
        filters=filters_ui('e')
        submitted=st.form_submit_button('Aplicar filtros',type='primary')
    if submitted or 'explore' not in st.session_state:
        try:
            st.session_state['explore']=structured(store,filters)
        except Exception as error:
            st.error(str(error))
    result=st.session_state.get('explore')
    if result:
        metrics(result['totals'])
        st.dataframe(pd.DataFrame(result['rows']),hide_index=True,width='stretch')
        st.caption('A localização é da oferta, não da sede. Uma oferta é uma combinação de curso, IES, território, modalidade e dimensão, conforme os IDs do repositório de origem.')
    with st.expander('Inventário do grafo'):
        st.dataframe(pd.DataFrame(store.stats()),hide_index=True)
    with st.expander('Algoritmos de grafo'):
        a,b = st.columns(2)
        if a.button('Calcular comunidades (Louvain)'):
            try:
                with st.spinner('Executando Louvain sobre a partição atual...'):
                    summary = louvain(store)
                st.session_state['louvain'] = summary
            except Exception as error:
                st.error(str(error))
        summary = st.session_state.get('louvain')
        if summary:
            st.caption(f"Algoritmo: {summary['algorithm']} · {summary['nodes']} nós · "
                       f"{summary['communities']} comunidades · propriedade `community` gravada no grafo.")
            st.dataframe(pd.DataFrame(summary['maiores']),hide_index=True,width='stretch')
        st.divider()
        st.write('Menor caminho entre duas entidades da partição (Cypher `shortestPath`, até 8 saltos).')
        catalog = store.query("MATCH (n:Entity) WHERE n.graph=$graph AND n.kind IN "
                              "['IES','Curso','Municipio','OfertaCurso'] "
                              "RETURN n.id AS id, n.name AS name, n.kind AS kind ORDER BY n.kind, n.name LIMIT 400")
        labels = {f"{row['name']} · {row['kind']} · {row['id']}": row['id'] for row in catalog}
        c,d = st.columns(2)
        origem = c.selectbox('Origem', list(labels), key='sp_origem')
        destino = d.selectbox('Destino', list(labels), key='sp_destino', index=min(1, len(labels)-1))
        if st.button('Encontrar menor caminho'):
            try:
                path = shortest_path(store, labels[origem], labels[destino])
                if path['found']:
                    st.session_state['shortest'] = path
                else:
                    st.session_state.pop('shortest', None)
                    st.info('Não há caminho de até 8 saltos entre essas entidades na partição atual.')
            except Exception as error:
                st.error(str(error))
        path = st.session_state.get('shortest')
        if path and path.get('found'):
            st.success(f"{path['saltos']} salto(s): {path['caminho']}")
            st.dataframe(pd.DataFrame(path['nos']),hide_index=True,width='stretch')

else:
    st.subheader('Microdados conectados, respostas rastreáveis')
    st.write('Projeto acadêmico de GraphRAG/KAG aplicado ao Censo da Educação Superior, sobre Neo4j 5 com modelo Labeled Property Graph: constraints de unicidade, índices de propriedade, full-text e vetorial (cosseno).')
    st.markdown('**Pipeline:** CSV LPG → validação e resolução por ID → Neo4j → texto + embeddings → fusão de rankings → travessia de até 2 saltos → evidências → resposta opcional com LLM.')
    st.write('Documentos são divididos em trechos, reconhecidos por dicionário de entidades e ligados por MENCIONA. Esse extrator não inventa relações como “oferece” a partir da presença de duas palavras.')
    st.write('A leitura pode ocorrer sem LLM. Embeddings semânticos usam um modelo multilíngue local. O modo hash é apenas uma linha de base lexical, sem compreensão semântica.')
    st.markdown('[Repositório dos dados](https://github.com/elieltondias/GraphRAG-KAG-Educacional) · [Documentação Neo4j](https://neo4j.com/docs/)')
    st.caption('Protótipo acadêmico local. O relatório de testes, a metodologia de avaliação e o roteiro de defesa estão na pasta docs/.')
