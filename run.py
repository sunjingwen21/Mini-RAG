#!/usr/bin/env python3
"""
Mini-RAG 个人知识库启动脚本
"""
import uvicorn
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    """启动服务器"""
    print("=" * 50)
    print("🚀 Mini-RAG 个人知识库")
    print("=" * 50)
    print()
    print("📌 功能特点:")
    print("   • 文档管理 - 创建、编辑、删除文档")
    print("   • 语义搜索 - 基于向量相似度的智能搜索")
    print("   • 智能问答 - 基于知识库的问答功能")
    print("   • 标签分类 - 支持标签管理和分类")
    print()
    print("🌐 访问地址: http://localhost:8000")
    print("📚 API 文档: http://localhost:8000/docs")
    print()
    print("按 Ctrl+C 停止服务器")
    print("=" * 50)
    print()
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"]
    )


if __name__ == "__main__":
    main()