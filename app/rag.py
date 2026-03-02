"""RAG 核心逻辑"""
import hashlib
import logging
import math
import re
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from app.config import (
    CHROMA_DIR,
    COLLECTION_NAME,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    LLM_EMBEDDING_MODEL,
    LLM_TIMEOUT_SECONDS,
    LLM_MAX_TOKENS_CONTEXT,
    LLM_MAX_TOKENS_FALLBACK,
)
from app.models import Document, SearchResult
from app.settings import settings_manager
from openai import OpenAI

try:
    import jieba
except Exception:
    jieba = None

logger = logging.getLogger("minirag.rag")


MATCH_STOPWORDS = {
    "什么", "是", "吗", "呢", "啊", "呀", "的", "了", "和", "与", "及", "请", "一下",
    "介绍", "一下子", "请问", "how", "what", "is", "are", "the", "a", "an"
}


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

class CustomOpenAIEmbeddingFunction(EmbeddingFunction):
    """自定义的新版 OpenAI 嵌入函数（适配 openai >= 1.0.0）"""
    def __init__(self, api_key: str, api_base: Optional[str] = None, model_name: str = "text-embedding-3-small"):
        self.api_key = api_key
        self.api_base = api_base
        self.model_name = model_name
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.api_base if self.api_base else None
        )

    def __call__(self, input: Documents) -> Embeddings:
        # 支持批量获取 embedding
        response = self.client.embeddings.create(
            input=input,
            model=self.model_name
        )
        return [data.embedding for data in response.data]


class LocalHashEmbeddingFunction(EmbeddingFunction):
    """本地分词哈希向量，避免远端 Embedding 不可用时整库退化为同一向量。"""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def _tokenize(self, text: str) -> List[str]:
        normalized = (text or "").lower().strip()
        if not normalized:
            return ["__empty__"]

        if jieba is not None:
            tokens = [token.strip() for token in jieba.lcut(normalized) if token.strip()]
            if tokens:
                return tokens

        return re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized) or [normalized]

    def _stable_bucket(self, token: str) -> Tuple[int, float]:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % self.dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        return index, sign

    def __call__(self, input: Documents) -> Embeddings:
        vectors: Embeddings = []

        for text in input:
            vec = [0.0] * self.dim

            for token in self._tokenize(text):
                index, sign = self._stable_bucket(token)
                vec[index] += sign

            norm = math.sqrt(sum(value * value for value in vec))
            if norm == 0:
                vec[0] = 1.0
                norm = 1.0

            vectors.append([value / norm for value in vec])

        return vectors


class VectorStore:
    """向量存储管理"""
    
    def __init__(self):
        try:
            self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        except Exception as e:
            logger.warning("检测到旧版或损坏的 Chroma 索引，正在重建本地向量库: %s", e)
            shutil.rmtree(CHROMA_DIR, ignore_errors=True)
            CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.embedding_function = self._build_embedding_function()
        self.collection = self._create_collection()
        self.splitter = TextSplitter()
        # 内存缓存可减少对底层查询实现差异的依赖，并让本地检索更稳定
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _build_embedding_function(self) -> EmbeddingFunction:
        """优先使用独立配置的 Embedding 服务；未配置时使用本地向量。"""
        settings = settings_manager.get_settings()
        embed_api_key = (settings.get("embedding_api_key") or "").strip()
        embed_base_url = (settings.get("embedding_base_url") or "").strip()
        embed_model = (settings.get("embedding_model") or "").strip()

        if not any([embed_api_key, embed_base_url, embed_model]):
            logger.info("未配置独立 Embedding 服务，使用本地分词哈希向量")
            return LocalHashEmbeddingFunction()

        if not embed_api_key:
            logger.warning("Embedding API Key 未配置，使用本地分词哈希向量")
            return LocalHashEmbeddingFunction()

        try:
            candidate = CustomOpenAIEmbeddingFunction(
                api_key=embed_api_key,
                api_base=embed_base_url or None,
                model_name=embed_model or LLM_EMBEDDING_MODEL
            )
            candidate(["test"])
            logger.info("已启用远端 Embedding 服务")
            return candidate
        except Exception as e:
            logger.warning("Embedding 服务不可用，转为本地分词哈希向量: %s", e)
            return LocalHashEmbeddingFunction()

    def _create_collection(self):
        return self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
            embedding_function=self.embedding_function
        )
    
    def _get_embedding(self, text: str) -> List[float]:
        """获取文本嵌入向量"""
        embedding = self.embedding_function([text])
        if embedding is not None and len(embedding) > 0:
            # 处理不同的返回格式
            if hasattr(embedding[0], 'tolist'):
                return embedding[0].tolist()
            elif isinstance(embedding[0], list):
                return embedding[0]
            else:
                return list(embedding[0])
        return []
    
    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """批量获取嵌入向量"""
        embeddings = self.embedding_function(texts)
        if embeddings is not None:
            result = []
            for e in embeddings:
                if hasattr(e, 'tolist'):
                    result.append(e.tolist())
                elif isinstance(e, list):
                    result.append(e)
                else:
                    result.append(list(e))
            return result
        return []

    def _cache_chunks(
        self,
        ids: List[str],
        chunks: List[str],
        metadatas: List[Dict[str, Any]],
        embeddings: List[List[float]]
    ):
        for chunk_id, chunk, metadata, embedding in zip(ids, chunks, metadatas, embeddings):
            self._cache[chunk_id] = {
                "embedding": embedding,
                "document": chunk,
                "metadata": metadata
            }

    def _score_similarity(self, left: List[float], right: List[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0

        cosine = sum(a * b for a, b in zip(left, right))
        # 归一化到 0~1，兼容前端显示和 Pydantic 校验。
        return max(0.0, min(1.0, (cosine + 1.0) / 2.0))
    
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
        self.collection.add(
            ids=ids,
            documents=chunks,
            metadatas=metadatas,
            embeddings=embeddings
        )
        self._cache_chunks(ids, chunks, metadatas, embeddings)
        
        return len(chunks)
    
    def update_document(self, document: Document) -> int:
        """更新文档（先删除旧的，再添加新的）"""
        self.delete_document(document.id)
        return self.add_document(document)
    
    def delete_document(self, doc_id: str):
        """删除文档的所有块"""
        prefix = f"{doc_id}_chunk_"
        stale_ids = [chunk_id for chunk_id in list(self._cache) if chunk_id.startswith(prefix)]

        if stale_ids:
            self.collection.delete(ids=stale_ids)

        for chunk_id in stale_ids:
            self._cache.pop(chunk_id, None)

    def rebuild(self, documents: List[Document]) -> int:
        """根据主文档存储全量重建索引。"""
        try:
            self.client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

        self.collection = self._create_collection()
        self._cache.clear()

        indexed_chunks = 0
        for document in documents:
            indexed_chunks += self.add_document(document)

        return indexed_chunks
    
    def search(self, query: str, limit: int = 5) -> List[Tuple[str, str, float, str, str, List[str]]]:
        """
        搜索相似内容
        返回: [(chunk_id, content, score, doc_id, title, tags), ...]
        """
        if not self._cache:
            return []

        query_embedding = self._get_embedding(query)
        if not query_embedding:
            return []

        search_results = []
        for chunk_id, entry in self._cache.items():
            metadata = entry["metadata"]
            score = self._score_similarity(query_embedding, entry["embedding"])

            search_results.append((
                chunk_id,
                entry["document"],
                score,
                metadata.get("doc_id", ""),
                metadata.get("title", ""),
                metadata.get("tags", "").split(",") if metadata.get("tags") else []
            ))

        search_results.sort(key=lambda item: item[2], reverse=True)
        return search_results[:limit]

    
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
        self._llm_client = None
        self._llm_client_cache_key: Tuple[str, str] = ("", "")
    
    def index_document(self, document: Document) -> int:
        """索引文档"""
        return self.vector_store.add_document(document)

    def update_document(self, document: Document) -> int:
        """更新已存在文档的索引。"""
        return self.vector_store.update_document(document)

    def rebuild_index(self, documents: List[Document]) -> int:
        """根据主存储全量重建索引。"""
        return self.vector_store.rebuild(documents)
    
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

    def _get_llm_client(self, api_key: str, base_url: str) -> OpenAI:
        cache_key = (api_key, base_url or "")
        if self._llm_client is not None and self._llm_client_cache_key == cache_key:
            return self._llm_client

        self._llm_client = OpenAI(
            api_key=api_key,
            base_url=base_url if base_url else None,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        self._llm_client_cache_key = cache_key
        logger.info("LLM client initialized for base_url=%s", base_url or "default")
        return self._llm_client
    
    def generate_answer(self, question: str, contexts: List[SearchResult]) -> str:
        """基于上下文生成答案"""
        # 动态读取当前配置
        settings = settings_manager.get_settings()
        api_key = settings.get("llm_api_key", "")
        base_url = settings.get("llm_base_url", "")
        model_name = settings.get("llm_model", "gpt-3.5-turbo")

        if api_key:
            try:
                client = self._get_llm_client(api_key, base_url)

                if contexts:
                    logger.info("Generating contextual answer with %d knowledge source(s)", len(contexts))
                    return self._generate_contextual_answer(question, contexts, client, model_name)

                logger.info("Knowledge miss confirmed, using LLM general fallback")
                return self._generate_general_answer(question, client, model_name)
            except Exception as e:
                logger.exception("LLM 生成失败: %s", e)
                if contexts:
                    return self._generate_fallback_answer(question, contexts)
                return "知识库中没有找到相关信息，大模型调用也失败了，请稍后重试。"

        if contexts:
            return self._generate_fallback_answer(question, contexts)

        return "知识库中没有找到相关信息，且当前未配置大模型，无法继续基于通用知识回答。"

    def _tokenize_for_match(self, text: str) -> List[str]:
        normalized = (text or "").lower().strip()
        if not normalized:
            return []

        if jieba is not None:
            raw_tokens = [token.strip().lower() for token in jieba.lcut(normalized) if token.strip()]
        else:
            raw_tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized)

        filtered = []
        for token in raw_tokens:
            if token in MATCH_STOPWORDS:
                continue
            if re.fullmatch(r"[a-z0-9_]+", token) and len(token) <= 1:
                continue
            filtered.append(token)
        return filtered

    def _has_knowledge_hit(self, question: str, contexts: List[SearchResult]) -> bool:
        """用关键词重叠判断知识库是否真的命中，避免低分误命中。"""
        if not contexts:
            return False

        query_tokens = self._tokenize_for_match(question)
        if not query_tokens:
            return bool(contexts)

        context_text = "\n".join(f"{ctx.title}\n{ctx.content}" for ctx in contexts).lower()
        context_tokens = set(self._tokenize_for_match(context_text))

        for token in query_tokens:
            if token in context_tokens:
                return True
            if len(token) > 1 and token in context_text:
                return True

        return False

    def _merge_completion_text(self, first_part: str, second_part: str) -> str:
        """拼接两段模型输出，尽量避免生硬断行。"""
        if not first_part:
            return second_part or ""
        if not second_part:
            return first_part

        if first_part.endswith(("\n", " ", "\t")) or second_part.startswith(("\n", " ", "\t")):
            return f"{first_part}{second_part}"

        return f"{first_part}\n{second_part}"

    def _create_chat_completion(
        self,
        client: OpenAI,
        model_name: str,
        messages: List[Dict[str, str]],
        max_tokens: int,
        log_label: str
    ) -> str:
        """执行一次对话补全，并在长度截断时自动续写一次。"""
        started_at = time.perf_counter()
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.2,
            max_tokens=max_tokens
        )
        elapsed = time.perf_counter() - started_at

        choice = response.choices[0] if response.choices else None
        message = getattr(choice, "message", None)
        content = (getattr(message, "content", None) or "").strip()
        finish_reason = getattr(choice, "finish_reason", None)
        logger.info(
            "LLM %s completion finished in %.2fs (finish_reason=%s)",
            log_label,
            elapsed,
            finish_reason or "unknown",
        )

        if finish_reason != "length":
            return content

        logger.warning(
            "LLM %s completion hit max_tokens=%d and was truncated, requesting one continuation",
            log_label,
            max_tokens,
        )

        continuation_messages = messages + [
            {"role": "assistant", "content": content},
            {
                "role": "user",
                "content": "请从刚才中断的位置继续回答，不要重复已经输出的内容，直接续写并完整结束。"
            }
        ]

        started_at = time.perf_counter()
        continuation_response = client.chat.completions.create(
            model=model_name,
            messages=continuation_messages,
            temperature=0.2,
            max_tokens=max_tokens
        )
        continuation_elapsed = time.perf_counter() - started_at

        continuation_choice = continuation_response.choices[0] if continuation_response.choices else None
        continuation_message = getattr(continuation_choice, "message", None)
        continuation_content = (getattr(continuation_message, "content", None) or "").strip()
        continuation_finish_reason = getattr(continuation_choice, "finish_reason", None)
        logger.info(
            "LLM %s continuation finished in %.2fs (finish_reason=%s)",
            log_label,
            continuation_elapsed,
            continuation_finish_reason or "unknown",
        )

        merged_content = self._merge_completion_text(content, continuation_content)
        if continuation_finish_reason == "length":
            logger.warning(
                "LLM %s continuation also hit max_tokens=%d; returning truncated content with notice",
                log_label,
                max_tokens,
            )
            notice = "\n\n[回答达到长度上限，内容可能未完整生成。请缩小问题范围，或在 .env 中提高 LLM_MAX_TOKENS_* 配置。]"
            return f"{merged_content.rstrip()}{notice}"

        return merged_content

    def _generate_contextual_answer(
        self,
        question: str,
        contexts: List[SearchResult],
        client: OpenAI,
        model_name: str
    ) -> str:
        """知识库命中时，基于上下文生成回答。"""
        context_texts = []
        for i, ctx in enumerate(contexts, 1):
            context_texts.append(f"【参考资料 {i}】标题: {ctx.title}\n内容: {ctx.content}")

        context_str = "\n\n".join(context_texts)
        system_prompt = (
            "你是一个专业、严谨且有用的个人知识库助手。"
            "请严格基于以下供参考的上下文信息来回答用户的问题。"
            "如果上下文信息不足以回答问题，请如实说明无法根据现有知识库回答，不要编造信息。"
            "重要排版与引用规则："
            "1. 必须使用 Markdown 格式(如加粗、列表、代码块)使回答结构清晰、层次分明、易于阅读。"
            "2. 当回答中参考了具体背景来源时，必须在引用的段落或句子末尾准确标注参考来源的编号，如 [1], [2] 等，以确保答案的严谨性。"
        )
        user_prompt = f"上下文信息：\n{context_str}\n\n用户问题：{question}"
        return self._create_chat_completion(
            client,
            model_name,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            LLM_MAX_TOKENS_CONTEXT,
            "contextual",
        )

    def _generate_general_answer(self, question: str, client: OpenAI, model_name: str) -> str:
        """知识库未命中时，使用通用模型回答。"""
        system_prompt = (
            "你是一个有用的通用助手。"
            "当前知识库没有命中相关内容。"
            "请直接回答用户问题，但必须明确说明这次回答不是来自知识库，而是通用模型回答。"
            "请使用清晰的 Markdown 格式。"
        )
        return self._create_chat_completion(
            client,
            model_name,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            LLM_MAX_TOKENS_FALLBACK,
            "fallback",
        )

    def _generate_fallback_answer(self, question: str, contexts: List[SearchResult]) -> str:
        """回退方案：如果未配置LLM或调用失败，返回简单的匹配结果"""
        answer_parts = [f"【此回答未接入大模型，为系统根据相似度自动提取的基础内容】\n根据知识库中的信息，查找到以下相关内容：\n"]
        
        for i, ctx in enumerate(contexts, 1):
            answer_parts.append(f"\n**参考 {i}** (来自《{ctx.title}》，相关度: {ctx.score:.2%})")
            answer_parts.append(f"\n{ctx.content}\n")
        
        answer_parts.append("\n💡 提示：您可以配置大模型(LLM_API_KEY等)以获得智能总结。")
        
        return "".join(answer_parts)
    
    def ask(
        self,
        question: str,
        context_limit: int = 3,
        allow_model_fallback: bool = False
    ) -> Tuple[str, List[SearchResult], bool, bool, bool]:
        """问答功能"""
        contexts = self.vector_store.get_context_for_question(question, limit=context_limit)
        knowledge_found = self._has_knowledge_hit(question, contexts)
        has_model = bool((settings_manager.get_settings().get("llm_api_key") or "").strip())

        if knowledge_found:
            logger.info("Knowledge hit for question=%r with %d source(s)", question, len(contexts))
            answer = self.generate_answer(question, contexts)
            return answer, contexts, True, False, False

        if has_model and not allow_model_fallback:
            logger.info("Knowledge miss for question=%r, requesting user confirmation for model fallback", question)
            return "知识库并不包含相关资料，是否调用模型继续询问？", [], False, True, False

        if has_model and allow_model_fallback:
            logger.info("User confirmed model fallback for question=%r", question)
            answer = self.generate_answer(question, [])
            return answer, [], False, False, True

        logger.info("Knowledge miss for question=%r and no LLM configured", question)
        return "知识库不存在该资料。", [], False, False, False


# 全局 RAG 引擎实例
rag_engine = RAGEngine()
