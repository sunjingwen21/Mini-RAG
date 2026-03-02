# 配置说明

Mini-RAG 使用项目根目录下的 `.env` 文件管理运行配置。

## 文件位置

请在项目根目录创建配置文件：

```text
mini-rag/
├── .env
├── .env.example
├── app/
└── ...
```

`start.sh` 启动时会自动读取这个文件。

## 快速配置

1. 复制模板文件

```bash
cp .env.example .env
```

2. 生成管理员访问令牌

```bash
openssl rand -hex 32
```

3. 将生成的随机字符串填入 `.env`

## 推荐的 `.env` 内容

```env
MINI_RAG_ADMIN_TOKEN=替换为你的长随机字符串
MINI_RAG_DEBUG=false
MINI_RAG_CORS_ORIGINS=http://localhost:8000

LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=gpt-3.5-turbo
LLM_EMBEDDING_MODEL=text-embedding-3-small
LLM_TIMEOUT_SECONDS=30
LLM_MAX_TOKENS_CONTEXT=1200
LLM_MAX_TOKENS_FALLBACK=800

MINI_RAG_LOG_LEVEL=INFO
```

## 配置项说明

### `MINI_RAG_ADMIN_TOKEN`

必填。用于保护所有 `/api/*` 接口。

- 未配置时，服务拒绝启动
- 浏览器首次打开页面时，会提示输入这个令牌
- 建议使用足够长的随机字符串，并妥善保管

### `MINI_RAG_DEBUG`

可选。控制开发模式开关。

- `false`：生产模式，关闭自动重载，关闭 `/docs`
- `true`：开发模式，开启自动重载，开放 `/docs`

公网部署建议保持为 `false`。

### `MINI_RAG_CORS_ORIGINS`

可选，但公网部署强烈建议配置。

- 使用逗号分隔多个允许访问的来源
- 示例：

```env
MINI_RAG_CORS_ORIGINS=https://rag.example.com,https://admin.example.com
```

只在本地调试时才建议留空。

### `LLM_BASE_URL`

可选。兼容 OpenAI 接口标准的上游地址。

示例：

```env
LLM_BASE_URL=https://api.openai.com/v1
```

或：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
```

### `LLM_API_KEY`

可选。上游模型提供商的 API Key。

- 只应保存在服务器本地
- 不要提交 `.env`
- 前端不会再回显真实密钥

### `LLM_MODEL`

可选。聊天模型名称。

示例：

```env
LLM_MODEL=gpt-4o-mini
```

### `LLM_EMBEDDING_MODEL`

可选。远程 Embedding 模型名称。

如果不配置远程 Embedding，本项目会自动回退到本地哈希向量。

### `LLM_TIMEOUT_SECONDS`

可选。上游大模型请求超时时间（秒）。

- 如果上游接口经常卡住，可以适当调低
- 如果设置过大，等待体感会更明显

### `LLM_MAX_TOKENS_CONTEXT`

可选。知识库命中时的最大输出长度。

- 值越小，通常返回越快
- 值越大，回答可以更长

### `LLM_MAX_TOKENS_FALLBACK`

可选。知识库未命中、转为通用模型回答时的最大输出长度。

### `MINI_RAG_LOG_LEVEL`

可选。应用日志级别。

常用值：

```env
MINI_RAG_LOG_LEVEL=INFO
```

或：

```env
MINI_RAG_LOG_LEVEL=DEBUG
```

## Linux 说明

如果你使用 `start.sh`，脚本会自动：

- 在缺少 `venv` 时创建虚拟环境
- 在缺少依赖时安装依赖
- 未配置 `MINI_RAG_ADMIN_TOKEN` 时拒绝启动
- 以后台方式启动服务
- 将日志写入 `log/app.log`、`log/access.log` 和 `log/launcher.log`
- 将进程 PID 写入 `log/minirag.pid`

`stop.sh` 是标准的 Linux 停止脚本。`stop.py` 仍可作为备用入口，二者都通过 `pkill` 停止运行中的服务。

## 公网部署最低建议

如果你要部署到公网，至少满足以下要求：

1. 配置 `MINI_RAG_ADMIN_TOKEN`
2. 配置 `MINI_RAG_DEBUG=false`
3. 将 `MINI_RAG_CORS_ORIGINS` 设置为你的真实域名
4. 使用 Nginx 或 Caddy 反向代理，并启用 HTTPS
5. `.env` 只保留在服务器上，不要提交到代码仓库
