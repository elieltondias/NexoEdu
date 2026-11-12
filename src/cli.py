import argparse
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from src.config import Settings
from src.store import Store
from src.ingest import ingest_lpg
from src.documents import ingest_document
from src.retrieval import Filters, retrieve, deterministic_answer

REPO = 'https://github.com/elieltondias/GraphRAG-KAG-Educacional.git'
COMMIT = '2dadee4abf4f358b9b274e84ca08b67a15351a66'

def download(path):
    path = Path(path)
    if path.exists():
        raise ValueError('Destino já existe. Use uma pasta nova ou importe a cópia existente. Nada foi sobrescrito.')
    subprocess.run(['git','lfs','version'],check=True)
    subprocess.run(['git','clone',REPO,str(path)],check=True)
    subprocess.run(['git','-C',str(path),'checkout',COMMIT],check=True)
    subprocess.run(['git','-C',str(path),'lfs','pull'],check=True)
    print('Repositório e Git LFS baixados na revisão fixada:',COMMIT)

def main():
    parser=argparse.ArgumentParser(description='NexoEdu · Neo4j / GraphRAG')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('download');p.add_argument('--path',default='data/repositorio')
    p=sub.add_parser('ingest');p.add_argument('--path',default='data/sample/lpg');p.add_argument('--scope',choices=['amostra','completa'],default='amostra');p.add_argument('--graph')
    p=sub.add_parser('document');p.add_argument('file');p.add_argument('--graph')
    p=sub.add_parser('ask');p.add_argument('question');p.add_argument('--uf',default='');p.add_argument('--municipio',default='');p.add_argument('--curso',default='');p.add_argument('--ies',default='');p.add_argument('--graph');p.add_argument('--out');p.add_argument('--structured',action='store_true')
    p=sub.add_parser('status');p.add_argument('--graph')
    args=parser.parse_args()
    try:
        if args.command=='download':
            download(args.path)
            return
        settings=Settings()
        if getattr(args,'graph',None):
            settings=replace(settings,graph=args.graph)
        store=Store(settings)
        if args.command=='ingest':
            ingest_lpg(store,args.path,args.scope)
        elif args.command=='document':
            p=Path(args.file)
            print(json.dumps(ingest_document(store,p.name,p.read_bytes()),ensure_ascii=False,indent=2))
        elif args.command=='ask':
            filters=Filters(args.uf,args.municipio,args.curso,args.ies) if args.structured else None
            result=retrieve(store,args.question,filters)
            result['answer']=deterministic_answer(result)
            print(result['answer'])
            if args.out:
                Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        else:
            print(json.dumps({'metadata':store.metadata(),'stats':store.stats()},ensure_ascii=False,indent=2))
    except Exception as error:
        parser.exit(1,f'Erro: {error}\n')

if __name__=='__main__':
    main()
