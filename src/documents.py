import hashlib
import io
import re
from collections import defaultdict
from pypdf import PdfReader
from src.embeddings import Embedder, normalize


def chunks(text, size=1100):
    text = re.sub(r'\s+',' ',text).strip()
    start = 0
    while start < len(text):
        end = min(start+size,len(text))
        if end < len(text):
            cut = text.rfind(' ',start+size//2,end)
            if cut > start:
                end = cut
        yield text[start:end].strip()
        start = end
        while start < len(text) and text[start].isspace():
            start += 1


def resolve_mentions(text, catalog):
    aliases = defaultdict(set)
    for row in catalog:
        for alias in [row['name'],row.get('alias')]:
            key = normalize(alias or '').strip()
            if len(key)>=3:
                aliases[key].add(row['id'])
    normalized = normalize(text)
    mentions = set()
    ambiguous = []
    for alias,ids in aliases.items():
        if re.search(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',normalized):
            if len(ids)==1:
                mentions.update(ids)
            else:
                ambiguous.append(alias)
    return sorted(mentions), sorted(ambiguous)


def alias_map(catalog):
    """Índice normalizado alias → conjunto de IDs canônicos."""
    aliases = defaultdict(set)
    for row in catalog:
        for alias in [row['name'], row.get('alias')]:
            key = normalize(alias or '').strip()
            if len(key) >= 3:
                aliases[key].add(row['id'])
    return aliases


def resolve_name(name, aliases):
    """Resolve um nome citado pelo LLM de forma exata; ambíguo/ausente retorna None."""
    candidates = {normalize(name).strip()}
    paren = re.match(r'^(.*?)\s*\((.*?)\)$', name.strip())
    if paren:
        candidates.update({normalize(paren.group(1)).strip(), normalize(paren.group(2)).strip()})
    ids = set()
    for candidate in candidates:
        if len(candidate) >= 3:
            ids.update(aliases.get(candidate, ()))
    if len(ids) == 1:
        return next(iter(ids))
    return None


def link_llm_extraction(store, chunk_id, page, source, data, catalog, aliases=None):
    """Vincula NER/RE do LLM ao grafo: MENCIONA e SE_RELACIONA_COM com procedência.

    Só entidades resolvidas exatamente no catálogo geram arestas; relações com
    extremos desconhecidos ou ambíguos são ignoradas e contabilizadas.
    """
    aliases = aliases if aliases is not None else alias_map(catalog)
    mencoes, vistos = [], set()
    for name in data.get('entidades', []):
        entity_id = resolve_name(name, aliases)
        if entity_id and entity_id not in vistos:
            vistos.add(entity_id)
            mencoes.append({'source': chunk_id, 'target': entity_id,
                            'props': {'metodo': 'llm', 'page': page}})
    relacoes, ignoradas = [], 0
    for relacao in data.get('relacoes', []):
        origem = resolve_name(relacao.get('origem', ''), aliases)
        destino = resolve_name(relacao.get('destino', ''), aliases)
        verbo = re.sub(r'[^a-z0-9 ]+', ' ', normalize(relacao.get('relacao', ''))).strip()[:40]
        if not origem or not destino or origem == destino or not verbo:
            ignoradas += 1
            continue
        relacoes.append({'source': origem, 'target': destino,
                         'props': {'relacao': verbo, 'trecho': chunk_id, 'metodo': 'llm',
                                   'source_file': source, 'page': page}})
    if mencoes:
        store.upsert_edges('MENCIONA', mencoes, props=True)
    if relacoes:
        store.upsert_edges('SE_RELACIONA_COM', relacoes, props=True)
    return {'mencoes': len(mencoes), 'relacoes': len(relacoes), 'ignoradas': ignoradas}


def ingest_document(store, name, content, llm=None):
    meta = store.metadata()
    embedder = Embedder(store.settings.embedding,store.settings.model)
    if meta.get('status')!='pronto' or meta.get('embedding_model')!=embedder.identity:
        raise ValueError('Importe os microdados com o mesmo modelo antes dos documentos.')
    if len(content)>15*1024*1024:
        raise ValueError('Limite de 15 MB por documento.')
    if name.lower().endswith('.pdf'):
        reader = PdfReader(io.BytesIO(content))
        if len(reader.pages)>100:
            raise ValueError('Limite de 100 páginas.')
        pages = [(i+1,p.extract_text() or '') for i,p in enumerate(reader.pages)]
    else:
        pages = [(1,content.decode('utf-8-sig'))]
    if not any(text.strip() for _,text in pages):
        raise ValueError('Documento sem texto. PDFs digitalizados precisam de OCR antes da importação.')
    digest = hashlib.sha256(content).hexdigest()
    doc_id = 'doc:'+digest
    props = {'id':doc_id,'kind':'Documento','name':name,'name_norm':normalize(name),'source_file':name,'sha256':digest}
    store.upsert_nodes('Documento',[{'id':doc_id,'props':props}])
    catalog = store.query("MATCH (n:Entity) WHERE n.graph=$graph AND n.kind IN ['IES','Curso','Municipio','UF','Regiao'] RETURN n.id AS id,n.name AS name,n.SG_IES AS alias")
    use_llm = bool(llm is not None and getattr(llm, 'enabled', False))
    aliases = alias_map(catalog) if use_llm else None
    LLM_CHUNK_LIMIT = 40
    count = mentions_count = 0
    mencoes_llm = relacoes_llm = relacoes_ignoradas = erros_llm = chunks_llm = 0
    ambiguities = set()
    for page,text in pages:
        for part,chunk in enumerate(chunks(text)):
            chunk_id = f'{doc_id}:p{page}:{part}'
            mentions,ambiguous = resolve_mentions(chunk,catalog)
            ambiguities.update(ambiguous)
            props = {'id':chunk_id,'kind':'Trecho','name':f'{name} · página {page} · trecho {part+1}',
                     'name_norm':normalize(name),'text':chunk,'search_text':normalize(chunk),'source_file':name,'page':page}
            store.upsert_nodes('Trecho',[{'id':chunk_id,'props':props}])
            store.upsert_edges('CONTEM',[{'source':doc_id,'target':chunk_id}])
            if mentions:
                store.upsert_edges('MENCIONA',[{'source':chunk_id,'target':i} for i in mentions])
            store.vectors([{'id':chunk_id,'vector':embedder.encode([chunk])[0]}])
            count += 1
            mentions_count += len(mentions)
            if use_llm and chunks_llm < LLM_CHUNK_LIMIT:
                chunks_llm += 1
                try:
                    extraction = llm.extract(chunk)
                    linked = link_llm_extraction(store, chunk_id, page, name, extraction, catalog, aliases)
                    mencoes_llm += linked['mencoes']
                    relacoes_llm += linked['relacoes']
                    relacoes_ignoradas += linked['ignoradas']
                except Exception:
                    erros_llm += 1
    store.wait_ready()
    metodo = 'NER por dicionário e RE de menção'
    if use_llm:
        metodo += '; NER/RE adicional via LLM (só vínculos resolvidos no catálogo)'
    metodo += '; não infere relações factuais por coocorrência.'
    return {'documento':name,'sha256':digest,'trechos':count,'mencoes':mentions_count,
            'mencoes_llm':mencoes_llm,'relacoes_llm':relacoes_llm,
            'relacoes_ignoradas':relacoes_ignoradas,'erros_llm':erros_llm,
            'chunks_com_llm':chunks_llm,'ambiguidades_nao_vinculadas':sorted(ambiguities),
            'metodo':metodo}
