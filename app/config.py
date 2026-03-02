"""配置文件"""
import os
from pathlib import Path


def _get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 数据目录
DATA_DIR = BASE_DIR / "data"
CHROMA_DIR = DATA_DIR / "chroma"
DOCS_DIR = DATA_DIR / "documents"

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# 向量数据库配置
COLLECTION_NAME = "knowledge_base"

# 嵌入模型配置
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# 服务器配置
HOST = "0.0.0.0"
PORT = 8000
DEBUG = _get_bool_env("MINI_RAG_DEBUG", False)

# 安全配置
ADMIN_TOKEN = os.getenv("MINI_RAG_ADMIN_TOKEN", "").strip()
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("MINI_RAG_CORS_ORIGINS", "").split(",")
    if origin.strip()
]

# LLM 配置 (OpenAI 兼容接口)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
LLM_EMBEDDING_MODEL = os.getenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small")

# 分块配置
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
