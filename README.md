# Mini-RAG 个人知识库

一个轻量级的个人知识库系统，基于 RAG（检索增强生成）技术，支持文档管理、语义搜索和智能问答。

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

### 启动服务

**方式一：命令行启动**
```bash
python run.py
```

**方式二：双击启动（Windows）**
```
双击 start.bat 文件
```

### 停止服务

**方式一：快捷键停止**
- 在运行终端按 `Ctrl + C`

**方式二：命令行停止**
```bash
python stop.py
```

**方式三：双击停止（Windows）**
```
双击 stop.bat 文件
```

### 访问应用

打开浏览器访问 http://localhost:8000

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