"""数据模型"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone


class DocumentCreate(BaseModel):
    """创建文档请求"""
    title: str = Field(..., min_length=1, max_length=200, description="文档标题")
    content: str = Field(..., min_length=1, description="文档内容")
    tags: List[str] = Field(default=[], description="标签列表")


class Document(DocumentCreate):
    """文档模型"""
    id: str = Field(..., description="文档ID")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="创建时间")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="更新时间")


class DocumentResponse(BaseModel):
    """文档响应"""
    id: str
    title: str
    content: str
    tags: List[str]
    created_at: datetime
    updated_at: datetime


class SearchResult(BaseModel):
    """搜索结果"""
    id: str
    title: str
    content: str
    score: float = Field(..., ge=0, le=1, description="相似度分数")
    tags: List[str]


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(..., min_length=1, description="搜索查询")
    limit: int = Field(default=5, ge=1, le=20, description="返回结果数量")


class QuestionRequest(BaseModel):
    """问答请求"""
    question: str = Field(..., min_length=1, description="问题内容")
    context_limit: int = Field(default=3, ge=1, le=10, description="上下文文档数量")
    allow_model_fallback: bool = Field(default=False, description="知识库未命中时是否允许调用通用模型")


class AnswerResponse(BaseModel):
    """问答响应"""
    question: str
    answer: str
    sources: List[SearchResult] = Field(default=[], description="参考来源")
    knowledge_found: bool = Field(default=True, description="知识库是否命中相关资料")
    needs_model_confirmation: bool = Field(default=False, description="是否需要用户确认调用模型")
    used_model_fallback: bool = Field(default=False, description="是否已使用通用模型回答")
    used_local_fallback: bool = Field(default=False, description="是否回退为知识库直接提取回答")
    model_name: str = Field(default="", description="本次实际调用的模型名称")
    answer_truncated: bool = Field(default=False, description="回答是否仍可能被长度上限截断")


class DocumentListResponse(BaseModel):
    """文档列表响应"""
    total: int
    documents: List[DocumentResponse]


class TagResponse(BaseModel):
    """标签响应"""
    name: str
    count: int


class MessageResponse(BaseModel):
    """通用消息响应"""
    message: str
    success: bool = True
