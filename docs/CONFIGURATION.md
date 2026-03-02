# Configuration

Mini-RAG uses a root-level `.env` file for deployment configuration.

## File Location

Create the file in the project root:

```text
mini-rag/
├── .env
├── .env.example
├── app/
└── ...
```

`start.sh` reads this file automatically before starting the service.

## Quick Setup

1. Copy the template:

```bash
cp .env.example .env
```

2. Generate a strong admin token:

```bash
openssl rand -hex 32
```

3. Paste the generated value into `.env`.

## Recommended `.env`

```env
MINI_RAG_ADMIN_TOKEN=replace-with-a-long-random-token
MINI_RAG_DEBUG=false
MINI_RAG_CORS_ORIGINS=http://localhost:8000

LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=gpt-3.5-turbo
LLM_EMBEDDING_MODEL=text-embedding-3-small
```

## Variable Reference

### `MINI_RAG_ADMIN_TOKEN`

Required. Protects all `/api/*` routes.

- If missing, the service refuses to start.
- The browser will ask for this token on first access.
- Use a long random value and keep it private.

### `MINI_RAG_DEBUG`

Optional. Controls development mode.

- `false`: production mode, `/docs` disabled, no auto reload
- `true`: development mode, `/docs` enabled, code auto reload enabled

Production should keep this set to `false`.

### `MINI_RAG_CORS_ORIGINS`

Optional but recommended for public deployment.

- Comma-separated origin whitelist
- Example:

```env
MINI_RAG_CORS_ORIGINS=https://rag.example.com,https://admin.example.com
```

Leave empty only for local debugging.

### `LLM_BASE_URL`

Optional. OpenAI-compatible API base URL.

Examples:

```env
LLM_BASE_URL=https://api.openai.com/v1
```

or

```env
LLM_BASE_URL=https://api.deepseek.com/v1
```

### `LLM_API_KEY`

Optional. Upstream model provider API key.

- Keep this only on the server
- Do not commit `.env`
- The frontend no longer reads back the real key value

### `LLM_MODEL`

Optional. Chat model name.

Example:

```env
LLM_MODEL=gpt-4o-mini
```

### `LLM_EMBEDDING_MODEL`

Optional. Remote embedding model name when remote embedding is enabled.

If you do not configure remote embedding, the project falls back to local hashed embeddings.

## Linux Note

If you use `start.sh`, the script will:

- create `venv` automatically if missing
- install dependencies automatically if needed
- refuse to start if `MINI_RAG_ADMIN_TOKEN` is not set

`stop.sh` is the standard Linux stop script. `stop.py` remains available as an alternate helper, and both use `pkill` to stop the running service.

## Public Deployment Baseline

For public-facing deployment, the minimum safe baseline is:

1. Set `MINI_RAG_ADMIN_TOKEN`
2. Set `MINI_RAG_DEBUG=false`
3. Set `MINI_RAG_CORS_ORIGINS` to your real domain
4. Put the app behind Nginx or Caddy with HTTPS
5. Keep `.env` on the server only
