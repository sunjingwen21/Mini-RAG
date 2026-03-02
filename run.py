#!/usr/bin/env python3
"""
Mini-RAG 个人知识库启动脚本
"""
import os
import uvicorn
import sys
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import DEBUG, HOST, PORT
from app.logging_config import configure_logging


def _get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main():
    """启动服务器"""
    log_config = configure_logging()
    logger = logging.getLogger("minirag.run")
    debug_mode = _get_bool_env("MINI_RAG_DEBUG", DEBUG)

    logger.info("=" * 50)
    logger.info("Mini-RAG startup")
    logger.info("Features: document management, semantic search, QA, tag management")
    logger.info("Server address: http://%s:%s", HOST, PORT)
    logger.info("Debug mode: %s", debug_mode)
    if debug_mode:
        logger.info("Docs address: http://%s:%s/docs", HOST, PORT)
    logger.info("=" * 50)

    run_options = {
        "app": "app.main:app",
        "host": HOST,
        "port": PORT,
        "reload": debug_mode,
        "log_config": log_config,
    }

    if debug_mode:
        run_options["reload_dirs"] = ["app"]

    uvicorn.run(**run_options)


if __name__ == "__main__":
    main()
