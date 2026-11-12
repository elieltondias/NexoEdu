import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

def _setting(name, default):
    return os.getenv(name, default)

@dataclass(frozen=True)
class Settings:
    host: str = field(default_factory=lambda: _setting('NEO4J_HOST', 'localhost'))
    port: int = field(default_factory=lambda: int(_setting('NEO4J_PORT', '7687')))
    user: str = field(default_factory=lambda: _setting('NEO4J_USER', 'neo4j'))
    password: str = field(default_factory=lambda: _setting('NEO4J_PASSWORD', 'nexoedu123'))
    database: str = field(default_factory=lambda: _setting('NEO4J_DATABASE', 'neo4j'))
    graph: str = field(default_factory=lambda: _setting('GRAPH_NAME', 'ensino_2024_amostra'))
    embedding: str = field(default_factory=lambda: _setting('EMBEDDING_MODE', 'semantic'))
    model: str = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
    llm_url: str = field(default_factory=lambda: _setting('LLM_BASE_URL', ''))
    llm_model: str = field(default_factory=lambda: _setting('LLM_MODEL', ''))
    llm_key: str = field(default_factory=lambda: _setting('LLM_API_KEY', ''))

    @property
    def uri(self):
        return f'bolt://{self.host}:{self.port}'
