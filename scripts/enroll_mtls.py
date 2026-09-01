"""One-time mTLS enrollment for comstar-game-ai against ada AO engine."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from secrets_loader import load_reach_enroll, material_dir, repo_root  # noqa: E402


async def main() -> int:
    cfg = load_reach_enroll()
    base_url = cfg["AO_BASE_URL"]
    cn = cfg.get("MTLS_CN", "comstar-game-ai")
    token = cfg.get("ENROLL_TOKEN", "").strip()
    if not token:
        print("ENROLL_TOKEN already spent or missing in .reach-enroll")
        return 1

    out = material_dir()
    out.mkdir(parents=True, exist_ok=True)

    from ao_reach.mtls_enroller import ReachMtlsEnroller
    from ao_reach.session_bridge import probe_health

    print(f"Enrolling CN={cn} to {base_url} -> {out}")
    material = await ReachMtlsEnroller().enroll(
        base_url=base_url,
        enroll_token=token,
        common_name=cn,
        material_dir=str(out),
        trust_enrollment_ca=True,
    )
    health = await probe_health(base_url, mtls=material.to_config())
    print(f"Enrollment OK. subject={material.subject} health={health}")

    # Invalidate spent token in enroll file (keep other settings).
    enroll_path = repo_root() / ".cursor" / "secrets" / ".reach-enroll"
    lines = []
    for line in enroll_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("ENROLL_TOKEN="):
            lines.append("ENROLL_TOKEN=")
        else:
            lines.append(line)
    enroll_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
