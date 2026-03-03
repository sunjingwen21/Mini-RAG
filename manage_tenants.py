"""Simple CLI for managing tenant registry."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from typing import Dict

from app.config import TENANT_REGISTRY_FILE


def _load_registry() -> Dict[str, Dict[str, object]]:
    TENANT_REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not TENANT_REGISTRY_FILE.exists():
        return {}

    try:
        with open(TENANT_REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_registry(registry: Dict[str, Dict[str, object]]) -> None:
    TENANT_REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TENANT_REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _usage() -> int:
    print("Usage:")
    print("  python manage_tenants.py list")
    print("  python manage_tenants.py add <tenant_id> <tenant_name> <access_token>")
    print("  python manage_tenants.py disable <tenant_id>")
    return 1


def _cmd_list() -> int:
    registry = _load_registry()
    if not registry:
        print("No tenants found.")
        return 0

    for tenant_id, item in sorted(registry.items()):
        print(
            f"{tenant_id}\tname={item.get('name', tenant_id)}\tenabled={item.get('enabled', True)}"
        )
    return 0


def _cmd_add(args: list[str]) -> int:
    if len(args) != 3:
        return _usage()

    tenant_id, tenant_name, access_token = args
    registry = _load_registry()
    registry[tenant_id] = {
        "id": tenant_id,
        "name": tenant_name,
        "enabled": True,
        "token_hash": _hash_secret(access_token),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_registry(registry)
    print(f"Tenant saved: {tenant_id}")
    print(f"Registry: {TENANT_REGISTRY_FILE}")
    return 0


def _cmd_disable(args: list[str]) -> int:
    if len(args) != 1:
        return _usage()

    tenant_id = args[0]
    registry = _load_registry()
    item = registry.get(tenant_id)
    if not isinstance(item, dict):
        print(f"Tenant not found: {tenant_id}")
        return 1

    item["enabled"] = False
    registry[tenant_id] = item
    _save_registry(registry)
    print(f"Tenant disabled: {tenant_id}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        return _usage()

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    if command == "list":
        return _cmd_list()
    if command == "add":
        return _cmd_add(args)
    if command == "disable":
        return _cmd_disable(args)
    return _usage()


if __name__ == "__main__":
    raise SystemExit(main())
