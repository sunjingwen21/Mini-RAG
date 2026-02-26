"""配置文件"""
import os
from pathlib import Path

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
DEBUG = True

# 分块配置
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50