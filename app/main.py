"""FastAPI 主应用"""
from typing import List
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.models import (
    DocumentCreate, DocumentResponse, DocumentListResponse,
    SearchRequest, SearchResult, QuestionRequest, AnswerResponse,
    TagResponse, MessageResponse
)
from app.database import document_store
from app.rag import rag_engine
from app.config import DEBUG

# 创建 FastAPI 应用
app = FastAPI(
    title="Mini-RAG 个人知识库",
    description="一个轻量级的个人知识库系统，支持文档管理、语义搜索和智能问答",
    version="1.0.0",
    debug=DEBUG
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件目录
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


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
    rag_engine.index_document(document)
    
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
    success = document_store.delete(doc_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 删除向量索引
    rag_engine.remove_document(doc_id)
    
    return MessageResponse(message="文档删除成功", success=True)


# ==================== 搜索 API ====================

@app.post("/api/search", response_model=List[SearchResult], summary="语义搜索")
async def search_documents(request: SearchRequest):
    """基于语义相似度搜索文档"""
    results = rag_engine.search(request.query, limit=request.limit)
    return results


# ==================== 问答 API ====================

@app.post("/api/ask", response_model=AnswerResponse, summary="智能问答")
async def ask_question(request: QuestionRequest):
    """基于知识库进行问答"""
    answer, sources = rag_engine.ask(request.question, context_limit=request.context_limit)
    
    return AnswerResponse(
        question=request.question,
        answer=answer,
        sources=sources
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


# 挂载静态文件
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")