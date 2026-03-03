"""FastAPI 主应用。"""
import hashlib
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import (
    AUTH_BLOCK_SECONDS,
    AUTH_FAILURE_WINDOW_SECONDS,
    AUTH_MAX_FAILURES,
    CORS_ORIGINS,
    DEBUG,
)
from app.models import (
    AnswerResponse,
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
    MessageResponse,
    QuestionRequest,
    SearchRequest,
    SearchResult,
    TagResponse,
)
from app.tenancy import session_manager, tenant_registry, tenant_runtime_manager

logger = logging.getLogger("minirag.api")
auth_failures = defaultdict(list)
auth_blocked_until: Dict[str, float] = {}


class SettingsRequest(BaseModel):
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""


class LoginRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=100)
    access_token: str = Field(..., min_length=1, max_length=500)


class LoginResponse(BaseModel):
    session_token: str
    expires_at: str
    tenant_id: str
    tenant_name: str


class TenantPublicInfo(BaseModel):
    id: str
    name: str


app = FastAPI(
    title="Mini-RAG 个人知识库",
    description="一个轻量级的个人知识库系统，支持文档管理、语义搜索和智能问答",
    version="1.0.0",
    debug=DEBUG,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Session-Token"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
AUTH_EXEMPT_PATHS = {"/api/auth/login", "/api/auth/tenants"}


def _get_client_ip(request: Request) -> str:
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


def _fingerprint(value: str) -> str:
    if not value:
        return "missing"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _to_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _prune_auth_tracking(now_ts: float, client_ip: str) -> List[float]:
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


def _record_auth_failure(
    client_ip: str,
    request: Request,
    token_fp: str,
    user_agent: str,
    reason: str,
) -> Optional[JSONResponse]:
    now_ts = time.time()
    failures = _prune_auth_tracking(now_ts, client_ip)
    failures.append(now_ts)
    auth_failures[client_ip] = failures
    failure_count = len(failures)

    if failure_count >= AUTH_MAX_FAILURES:
        auth_blocked_until[client_ip] = now_ts + AUTH_BLOCK_SECONDS
        logger.error(
            "Auth rate limit triggered: ip=%s method=%s path=%s token_fp=%s user_agent=%r reason=%s failure_count=%s window_seconds=%s block_seconds=%s",
            client_ip,
            request.method,
            request.url.path,
            token_fp,
            user_agent,
            reason,
            failure_count,
            AUTH_FAILURE_WINDOW_SECONDS,
            AUTH_BLOCK_SECONDS,
        )
        return JSONResponse(
            status_code=429,
            content={"detail": "认证失败次数过多，请稍后重试"},
        )

    logger.warning(
        "Unauthorized request rejected: ip=%s method=%s path=%s token_fp=%s user_agent=%r reason=%s failure_count=%s remaining_before_block=%s",
        client_ip,
        request.method,
        request.url.path,
        token_fp,
        user_agent,
        reason,
        failure_count,
        max(AUTH_MAX_FAILURES - failure_count, 0),
    )
    return None


def _clear_auth_failures(client_ip: str, request: Request, user_agent: str):
    if client_ip in auth_failures or client_ip in auth_blocked_until:
        logger.info(
            "Successful authentication after prior failures: ip=%s method=%s path=%s user_agent=%r",
            client_ip,
            request.method,
            request.url.path,
            user_agent,
        )
        auth_failures.pop(client_ip, None)
        auth_blocked_until.pop(client_ip, None)


def _extract_session_token(request: Request) -> str:
    return (
        request.headers.get("x-session-token")
        or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    )


def _get_tenant_context(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录或会话已失效")
    try:
        return tenant_runtime_manager.get_context(tenant_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="租户不存在")


@app.middleware("http")
async def require_session(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path not in AUTH_EXEMPT_PATHS:
        client_ip = _get_client_ip(request)
        user_agent = (request.headers.get("user-agent") or "").strip()
        now_ts = time.time()
        token = _extract_session_token(request)
        token_fp = _fingerprint(token)

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
                content={"detail": "认证失败次数过多，请稍后重试"},
            )

        session = session_manager.get_session(token)
        if not session:
            rate_limit_response = _record_auth_failure(
                client_ip,
                request,
                token_fp,
                user_agent,
                "invalid_or_expired_session",
            )
            if rate_limit_response:
                return rate_limit_response

            return JSONResponse(
                status_code=401,
                content={"detail": "会话无效或已过期"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        request.state.session_token = token
        request.state.tenant_id = session["tenant_id"]
        request.state.tenant_name = session.get("tenant_name", session["tenant_id"])
        _clear_auth_failures(client_ip, request, user_agent)

    response = await call_next(request)

    if request.method == "GET" and (
        request.url.path == "/" or request.url.path.startswith("/static/")
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


@app.on_event("startup")
async def startup():
    tenants = tenant_registry.list_tenants()
    if not tenants:
        raise RuntimeError(
            "未配置任何租户。请设置 MINI_RAG_ADMIN_TOKEN 作为默认租户，或在 data/tenants/tenants.json 中创建租户。"
        )

    summaries = tenant_runtime_manager.warmup_all()
    for summary in summaries:
        logger.info(
            "租户向量索引已同步: tenant_id=%s indexed_chunks=%s",
            summary["tenant_id"],
            summary["indexed_chunks"],
        )


@app.get("/")
async def root():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Mini-RAG API 服务运行中，请访问前端页面"}


@app.get("/api/auth/tenants", response_model=List[TenantPublicInfo], summary="获取可登录租户列表")
async def list_public_tenants():
    return [TenantPublicInfo(**tenant) for tenant in tenant_registry.list_tenants()]


@app.post("/api/auth/login", response_model=LoginResponse, summary="登录并创建会话")
async def login(request: Request, payload: LoginRequest):
    client_ip = _get_client_ip(request)
    user_agent = (request.headers.get("user-agent") or "").strip()
    now_ts = time.time()
    token_fp = _fingerprint(payload.access_token)

    _prune_auth_tracking(now_ts, client_ip)
    blocked_until = auth_blocked_until.get(client_ip)
    if blocked_until and blocked_until > now_ts:
        return JSONResponse(
            status_code=429,
            content={"detail": "认证失败次数过多，请稍后重试"},
        )

    tenant = tenant_registry.get_tenant(payload.tenant_id.strip())
    if not tenant or not tenant_registry.verify_access_token(payload.tenant_id.strip(), payload.access_token):
        rate_limit_response = _record_auth_failure(
            client_ip,
            request,
            token_fp,
            user_agent,
            "invalid_tenant_or_token",
        )
        if rate_limit_response:
            return rate_limit_response
        raise HTTPException(status_code=401, detail="租户或访问令牌无效")

    _clear_auth_failures(client_ip, request, user_agent)
    session_info = session_manager.create_session(
        tenant_id=payload.tenant_id.strip(),
        tenant_name=str(tenant.get("name") or payload.tenant_id.strip()),
        client_ip=client_ip,
        user_agent=user_agent,
    )
    logger.info(
        "Session created: tenant_id=%s ip=%s user_agent=%r expires_at=%s",
        session_info["tenant_id"],
        client_ip,
        user_agent,
        session_info["expires_at"],
    )
    return LoginResponse(**session_info)


@app.post("/api/auth/logout", response_model=MessageResponse, summary="退出当前会话")
async def logout(request: Request):
    session_token = getattr(request.state, "session_token", "")
    session_manager.revoke_session(session_token)
    return MessageResponse(message="已退出登录", success=True)


@app.post("/api/documents", response_model=DocumentResponse, summary="创建文档")
async def create_document(request: Request, doc_create: DocumentCreate):
    context = _get_tenant_context(request)
    document = context.document_store.create(doc_create)
    context.rag_engine.index_document(document)
    logger.info(
        "API create_document succeeded: tenant_id=%s id=%s title=%s",
        context.tenant_id,
        document.id,
        document.title,
    )
    return DocumentResponse(
        id=document.id,
        title=document.title,
        content=document.content,
        tags=document.tags,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@app.get("/api/documents", response_model=DocumentListResponse, summary="获取文档列表")
async def list_documents(
    request: Request,
    skip: int = Query(0, ge=0, description="跳过的文档数量"),
    limit: int = Query(20, ge=1, le=100, description="返回的文档数量"),
    tag: str = Query(None, description="按标签筛选"),
):
    context = _get_tenant_context(request)
    all_docs = context.document_store.get_all()

    if tag:
        all_docs = [doc for doc in all_docs if tag in doc.tags]

    all_docs.sort(key=lambda x: _to_utc_datetime(x.updated_at), reverse=True)
    total = len(all_docs)
    docs = all_docs[skip:skip + limit]

    safe_documents = []
    for doc in docs:
        try:
            safe_documents.append(
                DocumentResponse(
                    id=doc.id,
                    title=doc.title,
                    content=doc.content,
                    tags=doc.tags,
                    created_at=doc.created_at,
                    updated_at=doc.updated_at,
                )
            )
        except Exception as exc:
            logger.exception(
                "Skipping invalid document during list_documents: tenant_id=%s doc_id=%s error=%s",
                context.tenant_id,
                getattr(doc, "id", "unknown"),
                exc,
            )

    return DocumentListResponse(total=total, documents=safe_documents)


@app.get("/api/documents/{doc_id}", response_model=DocumentResponse, summary="获取文档详情")
async def get_document(request: Request, doc_id: str):
    context = _get_tenant_context(request)
    document = context.document_store.get(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")

    return DocumentResponse(
        id=document.id,
        title=document.title,
        content=document.content,
        tags=document.tags,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@app.put("/api/documents/{doc_id}", response_model=DocumentResponse, summary="更新文档")
async def update_document(request: Request, doc_id: str, doc_create: DocumentCreate):
    context = _get_tenant_context(request)
    document = context.document_store.update(doc_id, doc_create)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")

    context.rag_engine.update_document(document)
    logger.info(
        "API update_document succeeded: tenant_id=%s id=%s title=%s",
        context.tenant_id,
        document.id,
        document.title,
    )
    return DocumentResponse(
        id=document.id,
        title=document.title,
        content=document.content,
        tags=document.tags,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@app.delete("/api/documents/{doc_id}", response_model=MessageResponse, summary="删除文档")
async def delete_document(request: Request, doc_id: str):
    context = _get_tenant_context(request)
    document = context.document_store.get(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")

    success = context.document_store.delete(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="文档不存在")

    try:
        context.rag_engine.remove_document(doc_id)
    except Exception as exc:
        logger.exception("删除向量索引失败，尝试重建索引: tenant_id=%s error=%s", context.tenant_id, exc)
        try:
            context.rag_engine.rebuild_index(context.document_store.get_all())
        except Exception as rebuild_error:
            logger.exception("重建向量索引失败: tenant_id=%s error=%s", context.tenant_id, rebuild_error)

    logger.info("API delete_document succeeded: tenant_id=%s id=%s", context.tenant_id, doc_id)
    return MessageResponse(message="文档删除成功", success=True)


@app.post("/api/search", response_model=List[SearchResult], summary="语义搜索")
async def search_documents(request: Request, payload: SearchRequest):
    context = _get_tenant_context(request)
    results = context.rag_engine.search(payload.query, limit=payload.limit)
    logger.info(
        "API search_documents tenant_id=%s query=%r results=%d",
        context.tenant_id,
        payload.query,
        len(results),
    )
    return results


@app.post("/api/ask", response_model=AnswerResponse, summary="智能问答")
async def ask_question(request: Request, payload: QuestionRequest):
    context = _get_tenant_context(request)
    answer, sources, knowledge_found, needs_model_confirmation, used_model_fallback, used_local_fallback, model_name, answer_truncated = context.rag_engine.ask(
        payload.question,
        context_limit=payload.context_limit,
        allow_model_fallback=payload.allow_model_fallback,
    )
    logger.info(
        "API ask_question tenant_id=%s question=%r sources=%d knowledge_found=%s needs_confirm=%s used_model_fallback=%s used_local_fallback=%s model_name=%s answer_truncated=%s",
        context.tenant_id,
        payload.question,
        len(sources),
        knowledge_found,
        needs_model_confirmation,
        used_model_fallback,
        used_local_fallback,
        model_name or "-",
        answer_truncated,
    )
    return AnswerResponse(
        question=payload.question,
        answer=answer,
        sources=sources,
        knowledge_found=knowledge_found,
        needs_model_confirmation=needs_model_confirmation,
        used_model_fallback=used_model_fallback,
        used_local_fallback=used_local_fallback,
        model_name=model_name,
        answer_truncated=answer_truncated,
    )


@app.get("/api/tags", response_model=List[TagResponse], summary="获取所有标签")
async def get_tags(request: Request):
    context = _get_tenant_context(request)
    tag_counts = context.document_store.get_all_tags()
    return [
        TagResponse(name=name, count=count)
        for name, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    ]


@app.get("/api/stats", summary="获取统计信息")
async def get_stats(request: Request):
    context = _get_tenant_context(request)
    docs = context.document_store.get_all()
    tags = context.document_store.get_all_tags()
    latest_date = docs[0].updated_at.date().isoformat() if docs else None
    return {
        "tenant_id": context.tenant_id,
        "tenant_name": context.tenant_name,
        "total_documents": len(docs),
        "total_tags": len(tags),
        "recent_documents": len([d for d in docs if d.updated_at.date().isoformat() == latest_date]) if latest_date else 0,
    }


@app.get("/api/settings", summary="获取当前大模型设置")
async def get_settings(request: Request):
    context = _get_tenant_context(request)
    current_settings = context.settings_manager.get_settings()
    current_settings["has_llm_api_key"] = bool(current_settings.get("llm_api_key"))
    current_settings["has_embedding_api_key"] = bool(current_settings.get("embedding_api_key"))
    current_settings["llm_api_key"] = ""
    current_settings["embedding_api_key"] = ""
    current_settings["tenant_id"] = context.tenant_id
    current_settings["tenant_name"] = context.tenant_name
    return current_settings


@app.post("/api/settings", response_model=MessageResponse, summary="更新大模型设置")
async def update_settings(request: Request, settings: SettingsRequest):
    context = _get_tenant_context(request)
    settings_payload = {
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "embedding_base_url": settings.embedding_base_url,
        "embedding_model": settings.embedding_model,
    }

    if settings.llm_api_key.strip():
        settings_payload["llm_api_key"] = settings.llm_api_key

    if settings.embedding_api_key.strip():
        settings_payload["embedding_api_key"] = settings.embedding_api_key

    success = context.settings_manager.save_settings(settings_payload)
    if not success:
        raise HTTPException(status_code=500, detail="保存设置失败")

    tenant_runtime_manager.reload_context(context.tenant_id)
    logger.info(
        "API settings updated: tenant_id=%s llm_base_url=%s llm_model=%s",
        context.tenant_id,
        settings.llm_base_url,
        settings.llm_model,
    )
    return MessageResponse(message="设置已保存", success=True)


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
