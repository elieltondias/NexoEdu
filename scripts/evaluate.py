import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.store import Store
from src.retrieval import retrieve

CASES=[
    {'question':'João Pessoa','expected':['2024:municipio_2507507']},
    {'question':'Universidade Federal da Paraíba','expected':['2024:ies_579']},
    {'question':'Centro Universitário de João Pessoa','expected':['2024:ies_352']},
    {'question':'Santa Rita','expected':['2024:municipio_2513703']},
    {'question':'Campina Grande','expected':['2024:municipio_2504009']},
]

def evaluate(store):
    results=[]
    for case in CASES:
        for mode in ['lexical','vector','hybrid']:
            start=time.perf_counter()
            result=retrieve(store,case['question'],mode=mode)
            hits=len(set(case['expected']) & set(result['seeds']))
            results.append({'question':case['question'],'mode':mode,'expected':case['expected'],
                'retrieved_seed_ids':result['seeds'],'entity_recall_at_4':hits/len(case['expected']),
                'latency_seconds':round(time.perf_counter()-start,4),
                'paths':len(result['evidence']),'nodes':len(result['graph']['nodes'])})
    return {'methodology':'Cinco consultas de entidade conhecida, sem LLM, amostra fixa. Recall das sementes em top-4; não mede exatidão de respostas, causalidade, ou generalização. Latências incluem aquecimento do modelo e são específicas da máquina.',
        'metadata':store.metadata(),'results':results}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',default='output/evaluation.json');args=p.parse_args()
    output=Path(args.out);output.parent.mkdir(parents=True,exist_ok=True)
    data=evaluate(Store());output.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(output)
