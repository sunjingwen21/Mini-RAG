"""FastAPI 主应用"""
import hashlib
import logging
import secrets
import time
from collections import defaultdict
from typing import List
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.models import (
    DocumentCreate, DocumentResponse, DocumentListResponse,
    SearchRequest, SearchResult, QuestionRequest, AnswerResponse,
    TagResponse, MessageResponse
)
from pydantic import BaseModel
from app.database import document_store
from app.settings import settings_manager
from app.rag import rag_engine
from app.config import (
    ADMIN_TOKEN,
    AUTH_BLOCK_SECONDS,
    AUTH_FAILURE_WINDOW_SECONDS,
    AUTH_MAX_FAILURES,
    CORS_ORIGINS,
    DEBUG,
)

logger = logging.getLogger("minirag.api")
auth_failures = defaultdict(list)
auth_blocked_until = {}

# 创建 FastAPI 应用
app = FastAPI(
    title="Mini-RAG 个人知识库",
    description="一个轻量级的个人知识库系统，支持文档管理、语义搜索和智能问答",
    version="1.0.0",
    debug=DEBUG,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Token"],
)

# 静态文件目录
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _get_client_ip(request: Request) -> str:
    """尽量获取真实客户端 IP。"""
    for header_name in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip"):
        header_value = (request.headers.get(header_name) or "").strip()
        if not header_value:
            continue
        if header_name == "x-forwarded-for":
            return header_value.split(",")[0].strip()
        return header_value

    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _token_fingerprint(token: str) -> str:
    """记录令牌指纹，避免日志泄露明文。"""
    if not token:
        return "missing"
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def _prune_auth_tracking(now_ts: float, client_ip: str) -> List[float]:
    """清理窗口外的失败记录，并返回当前 IP 的有效失败列表。"""
    failures = [
        ts for ts in auth_failures.get(client_ip, [])
        if now_ts - ts <= AUTH_FAILURE_WINDOW_SECONDS
    ]
    if failures:
        auth_failures[client_ip] = failures
    elif client_ip in auth_failures:
        del auth_failures[client_ip]

    blocked_until = auth_blocked_until.get(client_ip)
    if blocked_until and blocked_until <= now_ts:
        del auth_blocked_until[client_ip]

    return failures


@app.middleware("http")
async def require_admin_token(request: Request, call_next):
    """保护所有 API 路由。"""
    if request.url.path.startswith("/api/"):
        client_ip = _get_client_ip(request)
        user_agent = (request.headers.get("user-agent") or "").strip()
        now_ts = time.time()
        provided_token = (
            request.headers.get("x-admin-token")
            or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        )
        token_fp = _token_fingerprint(provided_token)

        _prune_auth_tracking(now_ts, client_ip)

        blocked_until = auth_blocked_until.get(client_ip)
        if blocked_until and blocked_until > now_ts:
            remaining_seconds = int(blocked_until - now_ts)
            logger.warning(
                "Blocked API request during auth cooldown: ip=%s method=%s path=%s token_fp=%s user_agent=%r remaining_seconds=%s",
                client_ip,
                request.method,
                request.url.path,
                token_fp,
                user_agent,
                remaining_seconds,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "认证失败次数过多，请稍后重试"}
            )

        if not ADMIN_TOKEN:
            logger.error(
                "Rejected API request because MINI_RAG_ADMIN_TOKEN is not configured: ip=%s method=%s path=%s user_agent=%r",
                client_ip,
                request.method,
                request.url.path,
                user_agent,
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "服务端未配置 MINI_RAG_ADMIN_TOKEN"}
            )

        if not provided_token or not secrets.compare_digest(provided_token, ADMIN_TOKEN):
            failures = auth_failures[client_ip]
            failures.append(now_ts)
            failure_count = len(failures)

            if failure_count >= AUTH_MAX_FAILURES:
                auth_blocked_until[client_ip] = now_ts + AUTH_BLOCK_SECONDS
                logger.error(
                    "Auth rate limit triggered: ip=%s method=%s path=%s token_fp=%s user_agent=%r failure_count=%s window_seconds=%s block_seconds=%s",
                    client_ip,
                    request.method,
                    request.url.path,
                    token_fp,
                    user_agent,
                    failure_count,
                    AUTH_FAILURE_WINDOW_SECONDS,
                    AUTH_BLOCK_SECONDS,
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "认证失败次数过多，请稍后重试"}
                )

            logger.warning(
                "Unauthorized API request rejected: ip=%s method=%s path=%s token_fp=%s user_agent=%r failure_count=%s remaining_before_block=%s",
                client_ip,
                request.method,
                request.url.path,
                token_fp,
                user_agent,
                failure_count,
                max(AUTH_MAX_FAILURES - failure_count, 0),
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "未授权访问"},
                headers={"WWW-Authenticate": "Bearer"}
            )

        if client_ip in auth_failures or client_ip in auth_blocked_until:
            logger.info(
                "Successful API authentication after prior failures: ip=%s method=%s path=%s user_agent=%r",
                client_ip,
                request.method,
                request.url.path,
                user_agent,
            )
            auth_failures.pop(client_ip, None)
            auth_blocked_until.pop(client_ip, None)

    return await call_next(request)


@app.on_event("startup")
async def sync_vector_index():
    """启动时根据主文档存储重建向量索引，避免 JSON 与 Chroma 脱节。"""
    if not ADMIN_TOKEN:
        raise RuntimeError("缺少 MINI_RAG_ADMIN_TOKEN，拒绝在未启用鉴权的情况下启动")

    indexed_chunks = rag_engine.rebuild_index(document_store.get_all())
    logger.info("向量索引已同步，共 %s 个分块", indexed_chunks)


# ==================== 页面路由 ====================

@app.get("/")
async def root():
    """返回主页面"""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Mini-RAG API 服务运行中，请访问前端页面"}


# ==================== 文档 API ====================

@app.post("/api/documents", response_model=DocumentResponse, summary="创建文档")
async def create_document(doc_create: DocumentCreate):
    """创建新文档并建立索引"""
    # 创建文档
    document = document_store.create(doc_create)
    
    # 建立向量索引
    rag_engine.index_document(document)
    logger.info("API create_document succeeded: id=%s title=%s", document.id, document.title)
    
    return DocumentResponse(
        id=document.id,
        title=document.title,
        content=document.content,
        tags=document.tags,
        created_at=document.created_at,
        updated_at=document.updated_at
    )


@app.get("/api/documents", response_model=DocumentListResponse, summary="获取文档列表")
async def list_documents(
    skip: int = Query(0, ge=0, description="跳过的文档数量"),
    limit: int = Query(20, ge=1, le=100, description="返回的文档数量"),
    tag: str = Query(None, description="按标签筛选")
):
    """获取文档列表"""
    all_docs = document_store.get_all()
    
    # 按标签筛选
    if tag:
        all_docs = [doc for doc in all_docs if tag in doc.tags]
    
    # 按更新时间排序
    all_docs.sort(key=lambda x: x.updated_at, reverse=True)
    
    # 分页
    total = len(all_docs)
    docs = all_docs[skip:skip + limit]
    
    return DocumentListResponse(
        total=total,
        documents=[
            DocumentResponse(
                id=doc.id,
                title=doc.title,
                content=doc.content,
                tags=doc.tags,
                created_at=doc.created_at,
                updated_at=doc.updated_at
            )
            for doc in docs
        ]
    )


@app.get("/api/documents/{doc_id}", response_model=DocumentResponse, summary="获取文档详情")
async def get_document(doc_id: str):
    """获取单个文档的详细信息"""
    document = document_store.get(doc_id)
    
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    return DocumentResponse(
        id=document.id,
        title=document.title,
        content=document.content,
        tags=document.tags,
        created_at=document.created_at,
        updated_at=document.updated_at
    )


@app.put("/api/documents/{doc_id}", response_model=DocumentResponse, summary="更新文档")
async def update_document(doc_id: str, doc_create: DocumentCreate):
    """更新文档内容和索引"""
    document = document_store.update(doc_id, doc_create)
    
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 更新向量索引
    rag_engine.update_document(document)
    logger.info("API update_document succeeded: id=%s title=%s", document.id, document.title)
    
    return DocumentResponse(
        id=document.id,
        title=document.title,
        content=document.content,
        tags=document.tags,
        created_at=document.created_at,
        updated_at=document.updated_at
    )


@app.delete("/api/documents/{doc_id}", response_model=MessageResponse, summary="删除文档")
async def delete_document(doc_id: str):
    """删除文档及其索引"""
    document = document_store.get(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")

    success = document_store.delete(doc_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 删除向量索引
    try:
        rag_engine.remove_document(doc_id)
    except Exception as e:
        logger.exception("删除向量索引失败，尝试重建索引: %s", e)
        try:
            rag_engine.rebuild_index(document_store.get_all())
        except Exception as rebuild_error:
            logger.exception("重建向量索引失败: %s", rebuild_error)
    logger.info("API delete_document succeeded: id=%s", doc_id)
    
    return MessageResponse(message="文档删除成功", success=True)


# ==================== 搜索 API ====================

@app.post("/api/search", response_model=List[SearchResult], summary="语义搜索")
async def search_documents(request: SearchRequest):
    """基于语义相似度搜索文档"""
    results = rag_engine.search(request.query, limit=request.limit)
    logger.info("API search_documents query=%r results=%d", request.query, len(results))
    return results


# ==================== 问答 API ====================

@app.post("/api/ask", response_model=AnswerResponse, summary="智能问答")
async def ask_question(request: QuestionRequest):
    """基于知识库进行问答"""
    answer, sources, knowledge_found, needs_model_confirmation, used_model_fallback, model_name, answer_truncated = rag_engine.ask(
        request.question,
        context_limit=request.context_limit,
        allow_model_fallback=request.allow_model_fallback
    )
    logger.info(
        "API ask_question question=%r sources=%d knowledge_found=%s needs_confirm=%s used_model_fallback=%s model_name=%s answer_truncated=%s",
        request.question,
        len(sources),
        knowledge_found,
        needs_model_confirmation,
        used_model_fallback,
        model_name or "-",
        answer_truncated,
    )
    
    return AnswerResponse(
        question=request.question,
        answer=answer,
        sources=sources,
        knowledge_found=knowledge_found,
        needs_model_confirmation=needs_model_confirmation,
        used_model_fallback=used_model_fallback,
        model_name=model_name,
        answer_truncated=answer_truncated
    )


# ==================== 标签 API ====================

@app.get("/api/tags", response_model=List[TagResponse], summary="获取所有标签")
async def get_tags():
    """获取所有标签及其使用次数"""
    tag_counts = document_store.get_all_tags()
    
    tags = [
        TagResponse(name=name, count=count)
        for name, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    ]
    
    return tags


# ==================== 统计 API ====================

@app.get("/api/stats", summary="获取统计信息")
async def get_stats():
    """获取知识库统计信息"""
    docs = document_store.get_all()
    tags = document_store.get_all_tags()
    
    return {
        "total_documents": len(docs),
        "total_tags": len(tags),
        "recent_documents": len([d for d in docs if d.updated_at.date().isoformat() == 
                                 docs[0].updated_at.date().isoformat()]) if docs else 0
    }

# ==================== 设置 API ====================

class SettingsRequest(BaseModel):
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""

@app.get("/api/settings", summary="获取当前大模型设置")
async def get_settings():
    current_settings = settings_manager.get_settings()
    current_settings["has_llm_api_key"] = bool(current_settings.get("llm_api_key"))
    current_settings["has_embedding_api_key"] = bool(current_settings.get("embedding_api_key"))
    current_settings["llm_api_key"] = ""
    current_settings["embedding_api_key"] = ""
    return current_settings

@app.post("/api/settings", response_model=MessageResponse, summary="更新大模型设置")
async def update_settings(settings: SettingsRequest):
    settings_payload = {
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "embedding_base_url": settings.embedding_base_url,
        "embedding_model": settings.embedding_model
    }

    if settings.llm_api_key.strip():
        settings_payload["llm_api_key"] = settings.llm_api_key

    if settings.embedding_api_key.strip():
        settings_payload["embedding_api_key"] = settings.embedding_api_key

    success = settings_manager.save_settings(settings_payload)
    
    if not success:
        raise HTTPException(status_code=500, detail="保存设置失败")
    logger.info("API settings updated: llm_base_url=%s llm_model=%s", settings.llm_base_url, settings.llm_model)
        
    return MessageResponse(message="设置已保存", success=True)


# 挂载静态文件
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
