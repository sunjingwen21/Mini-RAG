# Mini-RAG 个人知识库

一个轻量级的个人知识库系统，基于 RAG（检索增强生成）技术，支持文档管理、语义搜索和智能问答。

当前仓库按 Linux 环境维护，开发和部署入口统一为 `start.sh` / `stop.sh`。

## 功能特点

- 📄 文档管理：支持上传和管理文本文档
- 🔍 语义搜索：基于向量相似度的智能搜索
- 💬 智能问答：基于知识库内容的 AI 问答
- 🏷️ 标签分类：支持标签管理和分类
- 💾 本地存储：数据存储在本地，保护隐私

## 技术栈

- **后端**: Python + FastAPI
- **向量数据库**: ChromaDB
- **嵌入模型**: ONNX MiniLM-L6-V2 (无需 PyTorch)
- **前端**: HTML/CSS/JavaScript (现代响应式设计)

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 安全配置（必需）

项目现在默认要求租户访问令牌，未配置时不会启动。最简单的方式是先用
`MINI_RAG_ADMIN_TOKEN` 自动创建一个 `default` 默认租户。

1. 复制环境变量模板

```bash
cp .env.example .env
```

2. 生成一个足够长的随机令牌

```bash
openssl rand -hex 32
```

3. 把生成的值写入 `.env`

```env
MINI_RAG_ADMIN_TOKEN=把这里替换成你的随机令牌
MINI_RAG_DEBUG=false
MINI_RAG_CORS_ORIGINS=http://localhost:8000
```

说明:
- `start.sh` 会自动读取项目根目录的 `.env`
- `start.sh` 会以后台方式启动服务，并把日志统一写到 `log/`
- 浏览器第一次打开页面时，会提示输入租户 ID 和访问令牌；如果只配置了 `MINI_RAG_ADMIN_TOKEN`，默认租户 ID 就是 `default`
- 公网部署时，把 `MINI_RAG_CORS_ORIGINS` 改成你的实际域名，例如 `https://rag.example.com`
- 更完整的配置说明见 `docs/CONFIGURATION.md`
- 中文配置说明见 `docs/CONFIGURATION.zh-CN.md`
- 默认会话有效期是 1 小时，可通过 `MINI_RAG_SESSION_TTL_SECONDS` 调整

### 启动服务

**方式一：前台启动（调试）**
```bash
python run.py
```

**方式二：后台启动（推荐）**
```bash
bash start.sh
```

查看日志：

```bash
tail -f log/app.log
tail -f log/access.log
tail -f log/launcher.log
```

### 停止服务

**方式一：快捷键停止**
- 仅在前台运行 `python run.py` 时使用 `Ctrl + C`

**方式二：命令行停止**
```bash
bash stop.sh
```

如果你需要，也可以继续使用 `python stop.py`；它同样基于 `pkill` 停止服务进程。

### 访问应用

打开浏览器访问 http://localhost:8000

首次访问会要求输入租户 ID 和访问令牌。只使用默认租户时，租户 ID 填 `default`，
访问令牌就是 `.env` 中配置的 `MINI_RAG_ADMIN_TOKEN`。

## 多租户数据存储

多租户采用文件隔离，每个租户独立存放文档、向量索引和模型配置。

- 租户注册表：`data/tenants/tenants.json`
- 会话数据：`data/sessions.json`
- 每个租户的文档：`data/tenants/<tenant_id>/documents/documents.json`
- 每个租户的模型配置：`data/tenants/<tenant_id>/settings.json`
- 每个租户的向量库：`data/tenants/<tenant_id>/chroma/`

`tenants.json` 的最小格式示例：

```json
{
  "default": {
    "id": "default",
    "name": "默认租户",
    "enabled": true,
    "token_hash": "把访问令牌做 sha256 后填这里",
    "created_at": "2026-03-03T00:00:00+00:00"
  }
}
```

如果你原来是单租户模式，首次访问 `default` 租户时，旧数据会自动迁移到
`data/tenants/default/` 下。

也可以直接用脚本管理租户：

```bash
python manage_tenants.py add team-a "团队 A" "这里填团队访问令牌"
python manage_tenants.py list
```

## 项目结构

```
mini-rag/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI 主应用
│   ├── models.py         # 数据模型
│   ├── database.py       # 数据库管理
│   ├── rag.py            # RAG 核心逻辑
│   └── config.py         # 配置文件
├── frontend/
│   ├── index.html        # 主页面
│   ├── css/
│   │   └── style.css     # 样式文件
│   └── js/
│       └── app.js        # 前端逻辑
├── data/                 # 数据存储目录
├── requirements.txt      # Python 依赖
├── run.py               # 启动脚本
└── README.md            # 项目说明
```

## 使用说明

1. **添加文档**: 点击"添加文档"按钮，输入标题和内容
2. **搜索**: 在搜索框输入关键词，系统会进行语义搜索
3. **问答**: 在问答框输入问题，系统会基于知识库回答

## 许可证

MIT License
