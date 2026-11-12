import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from src.embeddings import Embedder, normalize
from src.store import identifier

NAMES = ['NO_IES','NO_CURSO','NO_MUNICIPIO','NO_UF','NO_REGIAO','NO_MANTENEDORA','NO_CINE_ROTULO','NO_CINE_AREA_DETALHADA','NO_CINE_AREA_ESPECIFICA','NO_CINE_AREA_GERAL','NO_MODALIDADE_ENSINO','NO_REDE','nome','name']
SEARCHABLE = {'IES','Curso','Municipio','UF','Regiao','CineRotulo','CineAreaGeral','CineAreaDetalhada','CineAreaEspecifica'}

def typed_row(row):
    props = {}
    for header, value in row.items():
        if header.startswith(':') or value == '':
            continue
        name, _, kind = header.partition(':')
        identifier(name)
        if kind in {'int','long'}:
            value = int(value)
        elif kind == 'boolean':
            if value not in {'true','false'}:
                raise ValueError(f'Booleano inválido em {header}: {value}')
            value = value == 'true'
        props[name] = value
    return props

def batched(items, size=100):
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch

def ingest_lpg(store, path, scope, embedder=None, progress=print):
    path = Path(path)
    if scope not in {'amostra','completa'}:
        raise ValueError('Escopo deve ser amostra ou completa')
    if (scope == 'amostra') != (path/'sample_manifest.json').exists():
        raise ValueError('O escopo informado não corresponde ao manifesto da pasta. Não rotule amostras como base completa.')
    files = sorted((path/'nos').rglob('*.csv'))
    if not files or not (path/'arestas').exists():
        raise ValueError('Informe a pasta lpg com nos/ e arestas/.')
    fingerprint = hashlib.sha256()
    for p in files + sorted((path/'arestas').rglob('*.csv')):
        with p.open('rb') as stream:
            is_pointer = stream.read(80).startswith(b'version https://git-lfs.github.com/spec/v1')
        if is_pointer:
            raise ValueError(f'{p.name} é ponteiro Git LFS. Execute git lfs pull antes de importar.')
        fingerprint.update(str(p.relative_to(path)).encode())
        with p.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):
                fingerprint.update(block)
    fingerprint = fingerprint.hexdigest()
    embedder = embedder or Embedder(store.settings.embedding, store.settings.model)
    old = store.metadata()
    if old and (old.get('scope') != scope or old.get('embedding_model') != embedder.identity or old.get('fingerprint') != fingerprint):
        raise ValueError('Este grafo contém outro escopo/modelo. Escolha novo GRAPH_NAME para evitar misturar dados.')
    store.schema()
    store.set_metadata({'scope':scope,'year':2024,'embedding_model':embedder.identity,'status':'importando','source':str(path),'fingerprint':fingerprint})
    node_count = edge_count = 0
    labels_seen = set()
    types_seen = set()
    for p in files:
        progress(f'Importando nós: {p.name}')
        with p.open(encoding='utf-8-sig', newline='') as f:
            for batch in batched(csv.DictReader(f), 150):
                by_label = defaultdict(list)
                for row in batch:
                    props = typed_row(row)
                    label = identifier(row[':LABEL'])
                    labels_seen.add(label)
                    raw_id = row[':ID']
                    name = next((str(props[k]) for k in NAMES if props.get(k)), raw_id)
                    props.update({'id':f'2024:{raw_id}','original_id':raw_id,'kind':label,'name':name,'name_norm':normalize(name),
                                  'source_file':str(p.relative_to(path)),'dataset_year':2024})
                    props['embedding_text'] = name + (f" ({props['SG_IES']})" if props.get('SG_IES') else '') + f'. Tipo: {label}.'
                    props['search_text'] = normalize(' '.join(str(props[k]) for k in props if k.startswith(('NO_','SG_')))+f' {name} {label}')
                    by_label[label].append({'id':props['id'],'props':props})
                for label, rows in by_label.items():
                    store.upsert_nodes(label, rows)
                node_count += len(batch)
    for p in sorted((path/'arestas').rglob('*.csv')):
        progress(f'Importando relações: {p.name}')
        with p.open(encoding='utf-8-sig', newline='') as f:
            for batch in batched(csv.DictReader(f), 500):
                by_type = defaultdict(list)
                for row in batch:
                    kind = identifier(row[':TYPE'])
                    types_seen.add(kind)
                    by_type[kind].append({'source':'2024:'+row[':START_ID'],'target':'2024:'+row[':END_ID']})
                for kind, rows in by_type.items():
                    store.upsert_edges(kind, rows)
                edge_count += len(batch)
    progress('Gerando embeddings das entidades pesquisáveis')
    for label in sorted(SEARCHABLE):
        last = ''
        while True:
            rows = store.query('MATCH (n:Entity) WHERE n.graph=$graph AND n.kind=$label AND n.id>$last RETURN n.id AS id,n.embedding_text AS text ORDER BY n.id LIMIT 64', {'label':label,'last':last})
            if not rows:
                break
            vectors = embedder.encode([r['text'] for r in rows])
            store.vectors([{'id':r['id'],'vector':v} for r,v in zip(rows,vectors)])
            last = rows[-1]['id']
    store.wait_ready()
    result = {'scope':scope,'year':2024,'status':'pronto','embedding_model':embedder.identity,
              'nodes_imported':node_count,'edges_imported':edge_count,'source':str(path),'fingerprint':fingerprint,
              'labels':sorted(labels_seen),'relacoes':sorted(types_seen)}
    store.set_metadata(result)
    progress(json.dumps(result,ensure_ascii=False))
    return result
