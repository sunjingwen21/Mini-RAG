"""多租户与会话管理。"""
import hashlib
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Dict, List, Optional

from app.config import (
    ADMIN_TOKEN,
    DATA_DIR,
    DOCS_DIR,
    SESSION_TTL_SECONDS,
    SESSIONS_FILE,
    TENANTS_DIR,
    TENANT_REGISTRY_FILE,
)
from app.database import DocumentStore
from app.rag import RAGEngine, VectorStore
from app.settings import SettingsManager

logger = logging.getLogger("minirag.tenancy")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
class TenantContext:
    tenant_id: str
    tenant_name: str
    base_dir: Path
    document_store: DocumentStore
    settings_manager: SettingsManager
    rag_engine: RAGEngine


class TenantRegistry:
    """租户注册表。"""

    def __init__(self, registry_file: Path = TENANT_REGISTRY_FILE):
        self.registry_file = registry_file
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._ensure_registry()

    def _ensure_registry(self):
        if self.registry_file.exists():
            return

        default_registry: Dict[str, Dict[str, object]] = {}
        if ADMIN_TOKEN:
            default_registry["default"] = {
                "id": "default",
                "name": "默认租户",
                "enabled": True,
                "token_hash": _hash_secret(ADMIN_TOKEN),
                "created_at": _utc_now().isoformat(),
            }

        self._write_registry(default_registry)

    def _read_registry(self) -> Dict[str, Dict[str, object]]:
        try:
            with open(self.registry_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            logger.exception("读取租户注册表失败: %s", self.registry_file)
            return {}

    def _write_registry(self, data: Dict[str, Dict[str, object]]):
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def list_tenants(self) -> List[Dict[str, str]]:
        registry = self._read_registry()
        result: List[Dict[str, str]] = []
        for tenant_id, item in registry.items():
            if not isinstance(item, dict) or not item.get("enabled", True):
                continue
            result.append({
                "id": str(item.get("id") or tenant_id),
                "name": str(item.get("name") or tenant_id),
            })
        result.sort(key=lambda item: item["id"])
        return result

    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, object]]:
        registry = self._read_registry()
        item = registry.get(tenant_id)
        if not isinstance(item, dict) or not item.get("enabled", True):
            return None
        return item

    def verify_access_token(self, tenant_id: str, access_token: str) -> bool:
        tenant = self.get_tenant(tenant_id)
        if not tenant or not access_token:
            return False
        expected_hash = str(tenant.get("token_hash") or "")
        if not expected_hash:
            return False
        provided_hash = _hash_secret(access_token)
        return secrets.compare_digest(provided_hash, expected_hash)


class SessionManager:
    """基于文件的简单会话管理。"""

    def __init__(self, sessions_file: Path = SESSIONS_FILE):
        self.sessions_file = sessions_file
        self.sessions_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._ensure_file()

    def _ensure_file(self):
        if not self.sessions_file.exists():
            with open(self.sessions_file, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)

    def _read_sessions(self) -> Dict[str, Dict[str, str]]:
        try:
            with open(self.sessions_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            logger.exception("读取会话文件失败: %s", self.sessions_file)
            return {}

    def _write_sessions(self, data: Dict[str, Dict[str, str]]):
        with open(self.sessions_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _purge_expired(self, sessions: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
        now = _utc_now()
        cleaned = {}
        for session_id, item in sessions.items():
            try:
                expires_at = datetime.fromisoformat(str(item.get("expires_at")))
            except Exception:
                continue
            if expires_at > now:
                cleaned[session_id] = item
        return cleaned

    def create_session(self, tenant_id: str, tenant_name: str, client_ip: str, user_agent: str) -> Dict[str, str]:
        with self._lock:
            sessions = self._purge_expired(self._read_sessions())
            session_id = secrets.token_urlsafe(32)
            now = _utc_now()
            expires_at = now + timedelta(seconds=SESSION_TTL_SECONDS)
            sessions[session_id] = {
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
            self._write_sessions(sessions)
            return {
                "session_token": session_id,
                "tenant_id": tenant_id,
                "tenant_name": tenant_name,
                "expires_at": expires_at.isoformat(),
            }

    def get_session(self, session_id: str) -> Optional[Dict[str, str]]:
        if not session_id:
            return None

        with self._lock:
            sessions = self._purge_expired(self._read_sessions())
            session = sessions.get(session_id)
            self._write_sessions(sessions)
            return session

    def revoke_session(self, session_id: str) -> bool:
        if not session_id:
            return False

        with self._lock:
            sessions = self._read_sessions()
            existed = session_id in sessions
            if existed:
                del sessions[session_id]
                self._write_sessions(sessions)
            return existed


class TenantRuntimeManager:
    """租户运行时上下文。"""

    def __init__(self, tenant_registry: TenantRegistry):
        self.tenant_registry = tenant_registry
        self._contexts: Dict[str, TenantContext] = {}
        self._lock = RLock()

    def _tenant_base_dir(self, tenant_id: str) -> Path:
        return TENANTS_DIR / tenant_id

    def _migrate_legacy_default_data(self, base_dir: Path):
        docs_target = base_dir / "documents" / "documents.json"
        settings_target = base_dir / "settings.json"
        chroma_target = base_dir / "chroma"

        if docs_target.exists() or settings_target.exists() or chroma_target.exists():
            return

        migrated = False

        legacy_docs = DOCS_DIR / "documents.json"
        if legacy_docs.exists():
            docs_target.parent.mkdir(parents=True, exist_ok=True)
            docs_target.write_text(legacy_docs.read_text(encoding="utf-8"), encoding="utf-8")
            migrated = True

        legacy_settings = DATA_DIR / "settings.json"
        if legacy_settings.exists():
            settings_target.parent.mkdir(parents=True, exist_ok=True)
            settings_target.write_text(legacy_settings.read_text(encoding="utf-8"), encoding="utf-8")
            migrated = True

        if migrated:
            logger.info("Migrated legacy single-tenant data into default tenant at %s", base_dir)

    def get_context(self, tenant_id: str) -> TenantContext:
        with self._lock:
            if tenant_id not in self._contexts:
                self._contexts[tenant_id] = self._build_context(tenant_id)
            return self._contexts[tenant_id]

    def _build_context(self, tenant_id: str) -> TenantContext:
        tenant = self.tenant_registry.get_tenant(tenant_id)
        if not tenant:
            raise KeyError(f"tenant not found: {tenant_id}")

        base_dir = self._tenant_base_dir(tenant_id)
        base_dir.mkdir(parents=True, exist_ok=True)

        if tenant_id == "default":
            self._migrate_legacy_default_data(base_dir)

        docs_file = base_dir / "documents" / "documents.json"
        settings_file = base_dir / "settings.json"
        chroma_dir = base_dir / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)

        settings_manager = SettingsManager(settings_file=settings_file)
        document_store = DocumentStore(docs_file=docs_file)
        vector_store = VectorStore(chroma_dir=str(chroma_dir), settings_provider=settings_manager)
        rag_engine = RAGEngine(vector_store=vector_store, settings_provider=settings_manager)

        return TenantContext(
            tenant_id=tenant_id,
            tenant_name=str(tenant.get("name") or tenant_id),
            base_dir=base_dir,
            document_store=document_store,
            settings_manager=settings_manager,
            rag_engine=rag_engine,
        )

    def reload_context(self, tenant_id: str) -> TenantContext:
        with self._lock:
            self._contexts[tenant_id] = self._build_context(tenant_id)
            return self._contexts[tenant_id]

    def warmup_all(self) -> List[Dict[str, object]]:
        summaries: List[Dict[str, object]] = []
        for tenant in self.tenant_registry.list_tenants():
            tenant_id = tenant["id"]
            try:
                context = self.get_context(tenant_id)
                indexed_chunks = context.rag_engine.rebuild_index(context.document_store.get_all())
                summaries.append({
                    "tenant_id": tenant_id,
                    "indexed_chunks": indexed_chunks,
                })
            except Exception:
                logger.exception("租户索引预热失败: tenant_id=%s", tenant_id)
                summaries.append({
                    "tenant_id": tenant_id,
                    "indexed_chunks": 0,
                })
        return summaries


tenant_registry = TenantRegistry()
session_manager = SessionManager()
tenant_runtime_manager = TenantRuntimeManager(tenant_registry)
