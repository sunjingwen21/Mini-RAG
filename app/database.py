"""数据库管理"""
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from app.config import DOCS_DIR
from app.models import Document, DocumentCreate


class DocumentStore:
    """文档存储管理"""
    
    def __init__(self):
        self.docs_file = DOCS_DIR / "documents.json"
        self._ensure_file()
        self._documents: Dict[str, Document] = {}
        self._load_documents()
    
    def _ensure_file(self):
        """确保文档文件存在"""
        if not self.docs_file.exists():
            self._save_to_file({})
    
    def _load_documents(self):
        """从文件加载文档"""
        try:
            with open(self.docs_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._documents = {
                    doc_id: Document(**doc_data) 
                    for doc_id, doc_data in data.items()
                }
        except (json.JSONDecodeError, KeyError):
            self._documents = {}
    
    def _save_to_file(self, data: Dict):
        """保存文档到文件"""
        with open(self.docs_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    
    def create(self, doc_create: DocumentCreate) -> Document:
        """创建新文档"""
        doc_id = str(uuid.uuid4())
        now = datetime.now()
        
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
            updated_at=datetime.now()
        )
        
        self._documents[doc_id] = document
        self._persist()
        
        return document
    
    def delete(self, doc_id: str) -> bool:
        """删除文档"""
        if doc_id not in self._documents:
            return False
        
        del self._documents[doc_id]
        self._persist()
        
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
                'created_at': doc.created_at.isoformat(),
                'updated_at': doc.updated_at.isoformat()
            }
            for doc_id, doc in self._documents.items()
        }
        self._save_to_file(data)


# 全局文档存储实例
document_store = DocumentStore()