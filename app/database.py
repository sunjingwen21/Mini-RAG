"""数据库管理"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pathlib import Path
from pydantic import ValidationError

from app.config import DOCS_DIR
from app.models import Document, DocumentCreate

logger = logging.getLogger("minirag.database")

class DocumentStore:
    """文档存储管理"""
    
    def __init__(self, docs_file: Optional[Path] = None):
        self.docs_file = docs_file or (DOCS_DIR / "documents.json")
        self.docs_file.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_file()
        self._documents: Dict[str, Document] = {}
        self._load_documents()
    
    def _ensure_file(self):
        """确保文档文件存在"""
        if not self.docs_file.exists():
            self._save_to_file({})

    @staticmethod
    def _ensure_utc_datetime(value: datetime) -> datetime:
        """把无时区时间统一补成 UTC，避免 naive/aware 混用。"""
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    
    def _load_documents(self):
        """从文件加载文档"""
        try:
            with open(self.docs_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                loaded_documents: Dict[str, Document] = {}
                invalid_count = 0
                normalized_count = 0

                if isinstance(data, dict):
                    items = data.items()
                elif isinstance(data, list):
                    items = ((item.get("id", str(index)), item) for index, item in enumerate(data) if isinstance(item, dict))
                else:
                    raise ValueError("unexpected documents payload type")

                for doc_id, doc_data in items:
                    try:
                        document = Document(**doc_data)
                        normalized_created_at = self._ensure_utc_datetime(document.created_at)
                        normalized_updated_at = self._ensure_utc_datetime(document.updated_at)

                        if (
                            normalized_created_at != document.created_at
                            or normalized_updated_at != document.updated_at
                        ):
                            normalized_count += 1
                            document = document.model_copy(
                                update={
                                    "created_at": normalized_created_at,
                                    "updated_at": normalized_updated_at,
                                }
                            )

                        loaded_documents[doc_id] = document
                    except (ValidationError, TypeError, ValueError) as exc:
                        invalid_count += 1
                        logger.warning("Skipping invalid document entry: file=%s doc_id=%s error=%s", self.docs_file, doc_id, exc)

                self._documents = loaded_documents
                if invalid_count:
                    logger.warning("Loaded documents with %d invalid record(s) skipped: %s", invalid_count, self.docs_file)
                if normalized_count:
                    logger.info(
                        "Normalized %d legacy document timestamp(s) to UTC: %s",
                        normalized_count,
                        self.docs_file,
                    )
                    self._persist()
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            logger.warning("Documents file is invalid, starting with an empty store: %s", self.docs_file)
            self._documents = {}
    
    def _save_to_file(self, data: Dict):
        """保存文档到文件"""
        with open(self.docs_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    
    def create(self, doc_create: DocumentCreate) -> Document:
        """创建新文档"""
        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        document = Document(
            id=doc_id,
            title=doc_create.title,
            content=doc_create.content,
            tags=doc_create.tags,
            created_at=now,
            updated_at=now
        )
        
        self._documents[doc_id] = document
        self._persist()
        logger.info("Document created: id=%s title=%s", document.id, document.title)
        
        return document
    
    def get(self, doc_id: str) -> Optional[Document]:
        """获取文档"""
        return self._documents.get(doc_id)
    
    def get_all(self) -> List[Document]:
        """获取所有文档"""
        return list(self._documents.values())
    
    def update(self, doc_id: str, doc_create: DocumentCreate) -> Optional[Document]:
        """更新文档"""
        if doc_id not in self._documents:
            return None
        
        existing = self._documents[doc_id]
        document = Document(
            id=doc_id,
            title=doc_create.title,
            content=doc_create.content,
            tags=doc_create.tags,
            created_at=existing.created_at,
            updated_at=datetime.now(timezone.utc)
        )
        
        self._documents[doc_id] = document
        self._persist()
        logger.info("Document updated: id=%s title=%s", document.id, document.title)
        
        return document
    
    def delete(self, doc_id: str) -> bool:
        """删除文档"""
        if doc_id not in self._documents:
            return False
        
        del self._documents[doc_id]
        self._persist()
        logger.info("Document deleted: id=%s", doc_id)
        
        return True
    
    def get_all_tags(self) -> Dict[str, int]:
        """获取所有标签及其使用次数"""
        tag_counts: Dict[str, int] = {}
        for doc in self._documents.values():
            for tag in doc.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return tag_counts
    
    def _persist(self):
        """持久化存储"""
        data = {
            doc_id: {
                'id': doc.id,
                'title': doc.title,
                'content': doc.content,
                'tags': doc.tags,
                'created_at': self._ensure_utc_datetime(doc.created_at).isoformat(),
                'updated_at': self._ensure_utc_datetime(doc.updated_at).isoformat()
            }
            for doc_id, doc in self._documents.items()
        }
        self._save_to_file(data)


# 全局文档存储实例
document_store = DocumentStore()
