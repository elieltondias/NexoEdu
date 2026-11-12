import hashlib
import math
import re
import unicodedata
from functools import lru_cache

DIMENSION = 384

def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text).lower()) if not unicodedata.combining(c))

STOP = set('a o as os e de da do das dos em na no nas nos para por um uma quais qual que como quantos quantas tem sao ha sobre me mostre explique'.split())

def tokens(text):
    return [t for t in re.findall(r'[a-z0-9]+', normalize(text)) if len(t) > 1 and t not in STOP]

@lru_cache(maxsize=2)
def semantic_model(identity):
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=identity, threads=2)

class Embedder:
    def __init__(self, mode='semantic', model='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'):
        if mode not in {'semantic', 'hash'}:
            raise ValueError('EMBEDDING_MODE deve ser semantic ou hash')
        self.mode = mode
        self.identity = model if mode == 'semantic' else 'hash-sha256-384-v1'
        self._model = None

    def encode(self, texts):
        if self.mode == 'semantic':
            if self._model is None:
                self._model = semantic_model(self.identity)
            return [v.tolist() for v in self._model.embed(texts)]
        result = []
        for text in texts:
            vector = [0.0] * DIMENSION
            for word in tokens(text):
                digest = hashlib.sha256(word.encode()).digest()
                vector[int.from_bytes(digest[:4], 'big') % DIMENSION] += 1.0
            if not any(vector):
                vector[0] = 1.0
            length = math.sqrt(sum(v*v for v in vector))
            result.append([v/length for v in vector])
        return result
