"""HTTP KB ingest for observable records; local JSONL for privileged."""

from __future__ import annotations

import json
import ssl
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from comstar_game_ai.agent.reach.client import reach_mtls_config
from comstar_game_ai.agent.records.privileged_store import PrivilegedRecord, PrivilegedStore
from comstar_game_ai.shared.config import load_config


def _ssl_context(config: dict[str, Any] | None = None) -> ssl.SSLContext:
    from ao_reach.mtls import load_reach_mtls_material

    cfg = config or load_config()
    material = load_reach_mtls_material(reach_mtls_config(cfg))
    ctx = ssl.create_default_context(cafile=None)
    # Write temp PEMs for urllib — material is in memory.
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="comstar-mtls-"))
    cert = tmp / "cert.pem"
    key = tmp / "key.pem"
    ca = tmp / "ca.pem"
    cert.write_text(material.client_cert_pem, encoding="utf-8")
    key.write_text(material.client_key_pem, encoding="utf-8")
    ca.write_text(material.ca_pem, encoding="utf-8")
    ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
    ctx.load_verify_locations(cafile=str(ca))
    return ctx


def ingest_observable(
    content: str,
    *,
    source_id: str = "experience_observable",
    user_goal: str = "comstar after-action",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_config()
    base = cfg["ao"]["base_url"].rstrip("/")
    payload = {
        "content": content,
        "source_id": source_id,
        "user_goal": user_goal,
        "fast": True,
    }
    req = Request(
        f"{base}/api/v1/kb/ingest",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    ctx = _ssl_context(cfg)
    with urlopen(req, context=ctx, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ingest_privileged(
    record: PrivilegedRecord | dict[str, Any],
    *,
    store: PrivilegedStore | None = None,
) -> dict[str, Any]:
    """Append privileged learning data to local JSONL only (C10 split)."""
    ps = store or PrivilegedStore()
    path = ps.append(record)
    return {"ok": True, "path": str(path), "channel": "local_privileged"}


def ingest_after_action(
    *,
    observable: dict[str, Any],
    privileged: dict[str, Any] | None = None,
    source_id: str = "experience_observable",
    user_goal: str = "comstar after-action",
    config: dict[str, Any] | None = None,
    privileged_store: PrivilegedStore | None = None,
) -> dict[str, Any]:
    """Split after-action record: observable -> AO KB, privileged -> local JSONL."""
    obs_payload = json.dumps({"type": "after_action", "observable": observable})
    obs_result = ingest_observable(
        obs_payload,
        source_id=source_id,
        user_goal=user_goal,
        config=config,
    )
    priv_result: dict[str, Any] | None = None
    if privileged is not None:
        priv_result = ingest_privileged(
            PrivilegedRecord(
                record_type=str(observable.get("type") or "after_action"),
                privileged=privileged,
                observable_ref=obs_result.get("id") or obs_result.get("record_id"),
                campaign_id=observable.get("campaign_id"),
                turn=observable.get("turn"),
            ),
            store=privileged_store,
        )
    return {"observable": obs_result, "privileged": priv_result}
