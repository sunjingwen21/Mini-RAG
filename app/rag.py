"""RAG 核心逻辑"""
import re
from typing import List, Tuple, Optional
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

from app.config import CHROMA_DIR, COLLECTION_NAME, CHUNK_SIZE, CHUNK_OVERLAP
from app.models import Document, SearchResult


class TextSplitter:
    """文本分块器"""
    
    def __init__(self, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def split_text(self, text: str) -> List[str]:
        """将文本分割成块"""
        # 按段落分割
        paragraphs = re.split(r'\n\s*\n', text)
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # 如果当前块加上新段落不超过限制，则添加
            if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
            else:
                # 保存当前块
                if current_chunk:
                    chunks.append(current_chunk)
                
                # 如果段落本身超过限制，需要进一步分割
                if len(para) > self.chunk_size:
                    sub_chunks = self._split_long_paragraph(para)
                    chunks.extend(sub_chunks[:-1])
                    current_chunk = sub_chunks[-1] if sub_chunks else ""
                else:
                    current_chunk = para
        
        # 添加最后一个块
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks if chunks else [text]
    
    def _split_long_paragraph(self, text: str) -> List[str]:
        """分割过长的段落"""
        sentences = re.split(r'([。！？.!?])', text)
        chunks = []
        current = ""
        
        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else "")
            
            if len(current) + len(sentence) <= self.chunk_size:
                current += sentence
            else:
                if current:
                    chunks.append(current)
                current = sentence
        
        if current:
            chunks.append(current)
        
        return chunks


class VectorStore:
    """向量存储管理"""
    
    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        # 使用默认的嵌入函数（不需要 PyTorch）
        self.embedding_function = embedding_functions.DefaultEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        self.splitter = TextSplitter()
    
    def _get_embedding(self, text: str) -> List[float]:
        """获取文本嵌入向量"""
        embedding = self.embedding_function([text])
        if embedding is not None and len(embedding) > 0:
            return embedding[0].tolist()
        return []
    
    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """批量获取嵌入向量"""
        embeddings = self.embedding_function(texts)
        if embeddings is not None:
            return [e.tolist() for e in embeddings]
        return []
    
    def add_document(self, document: Document) -> int:
        """添加文档到向量存储"""
        chunks = self.splitter.split_text(document.content)
        
        if not chunks:
            return 0
        
        ids = []
        metadatas = []
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"{document.id}_chunk_{i}"
            ids.append(chunk_id)
            metadatas.append({
                "doc_id": document.id,
                "title": document.title,
                "chunk_index": i,
                "tags": ",".join(document.tags)
            })
        
        embeddings = self._get_embeddings(chunks)
        
        if embeddings:
            self.collection.add(
                ids=ids,
                documents=chunks,
                embeddings=embeddings,
                metadatas=metadatas
            )
        else:
            # 如果无法获取嵌入向量，让 ChromaDB 自动处理
            self.collection.add(
                ids=ids,
                documents=chunks,
                metadatas=metadatas
            )
        
        return len(chunks)
    
    def update_document(self, document: Document) -> int:
        """更新文档（先删除旧的，再添加新的）"""
        self.delete_document(document.id)
        return self.add_document(document)
    
    def delete_document(self, doc_id: str):
        """删除文档的所有块"""
        # 获取所有该文档的块ID
        results = self.collection.get(
            where={"doc_id": doc_id}
        )
        
        if results['ids']:
            self.collection.delete(ids=results['ids'])
    
    def search(self, query: str, limit: int = 5) -> List[Tuple[str, str, float, str, str, List[str]]]:
        """
        搜索相似内容
        返回: [(chunk_id, content, score, doc_id, title, tags), ...]
        """
        query_embedding = self._get_embedding(query)
        
        if query_embedding:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit
            )
        else:
            results = self.collection.query(
                query_texts=[query],
                n_results=limit
            )
        
        search_results = []
        
        if results['ids'] and results['ids'][0]:
            for i, chunk_id in enumerate(results['ids'][0]):
                content = results['documents'][0][i] if results['documents'] else ""
                metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                distance = results['distances'][0][i] if results['distances'] else 0
                
                # 将距离转换为相似度分数 (1 - distance for cosine)
                score = 1 - distance
                
                doc_id = metadata.get('doc_id', '')
                title = metadata.get('title', '')
                tags = metadata.get('tags', '').split(',') if metadata.get('tags') else []
                
                search_results.append((chunk_id, content, score, doc_id, title, tags))
        
        return search_results
    
    def get_context_for_question(self, question: str, limit: int = 3) -> List[SearchResult]:
        """获取问题的相关上下文"""
        results = self.search(question, limit=limit)
        
        contexts = []
        seen_docs = set()
        
        for chunk_id, content, score, doc_id, title, tags in results:
            # 去重，每个文档只取最相关的一个块
            if doc_id not in seen_docs:
                seen_docs.add(doc_id)
                contexts.append(SearchResult(
                    id=doc_id,
                    title=title,
                    content=content,
                    score=score,
                    tags=tags
                ))
        
        return contexts


class RAGEngine:
    """RAG 引擎"""
    
    def __init__(self):
        self.vector_store = VectorStore()
    
    def index_document(self, document: Document) -> int:
        """索引文档"""
        return self.vector_store.add_document(document)
    
    def remove_document(self, doc_id: str):
        """从索引中移除文档"""
        self.vector_store.delete_document(doc_id)
    
    def search(self, query: str, limit: int = 5) -> List[SearchResult]:
        """搜索相关文档"""
        results = self.vector_store.search(query, limit)
        
        search_results = []
        seen_docs = set()
        
        for chunk_id, content, score, doc_id, title, tags in results:
            if doc_id not in seen_docs:
                seen_docs.add(doc_id)
                search_results.append(SearchResult(
                    id=doc_id,
                    title=title,
                    content=content,
                    score=round(score, 4),
                    tags=tags
                ))
        
        return search_results
    
    def generate_answer(self, question: str, contexts: List[SearchResult]) -> str:
        """基于上下文生成答案（简化版，不使用外部LLM）"""
        if not contexts:
            return "抱歉，我在知识库中没有找到相关的信息来回答您的问题。"
        
        # 构建简单的回答
        answer_parts = [f"根据知识库中的信息，以下是与您问题相关的内容：\n"]
        
        for i, ctx in enumerate(contexts, 1):
            answer_parts.append(f"\n**参考 {i}** (来自《{ctx.title}》，相关度: {ctx.score:.2%})")
            answer_parts.append(f"\n{ctx.content}\n")
        
        answer_parts.append("\n💡 提示：您可以查看上述参考资料获取更详细的信息。")
        
        return "".join(answer_parts)
    
    def ask(self, question: str, context_limit: int = 3) -> Tuple[str, List[SearchResult]]:
        """问答功能"""
        contexts = self.vector_store.get_context_for_question(question, limit=context_limit)
        answer = self.generate_answer(question, contexts)
        return answer, contexts


# 全局 RAG 引擎实例
rag_engine = RAGEngine()