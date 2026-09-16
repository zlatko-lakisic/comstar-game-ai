#!/usr/bin/env python3
"""F6: replay the Segesta fixture payload against candidate models.

Usage (on the box that hosts Ollama, typically ada):

    python scripts/replay_director_models.py
    python scripts/replay_director_models.py --models qwen3.6:27b,phi4:14b --samples 10

Writes a markdown table under the fixture directory. Temperature is forced to 0.
Does not change the shipped overlay model — that decision is section 6.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

from comstar_game_ai.agent.belief.store import BeliefStore
from comstar_game_ai.agent.campaign_ids import CampaignIdMap
from comstar_game_ai.agent.campaign_payload import compose_campaign_payload
from comstar_game_ai.agent.campaign_vocab import STABLE_DIRECTOR_BACKSTORY
from comstar_game_ai.agent.reach.prompts import campaign_directive_question
from comstar_game_ai.shared.config import repo_root

FIXTURE = (
    repo_root()
    / "tests"
    / "fixtures"
    / "campaign_runs"
    / "20260909-220705"
)

DEFAULT_MODELS = (
    "qwen3.6:27b",
    "gemma4:26b",
    "qwen3.5:27b",
    "phi4:14b",
    "qwen3.5:9b",
    "ministral-3:8b",
    "llama3.1:8b",
)


def _compose_prompt() -> tuple[str, str]:
    belief = BeliefStore.load(FIXTURE / "belief" / "belief_snapshot.json")
    id_map = CampaignIdMap.load(FIXTURE / "runtime" / "campaign_id_map.json")
    payload = compose_campaign_payload(
        belief=belief,
        id_map=id_map,
        turn=2,
        question_id="campaign-2-replay",
        player_faction="julii",
    )
    question = campaign_directive_question(2, "julii", question_id=payload.question_id)
    prompt = (
        f"{STABLE_DIRECTOR_BACKSTORY}\n\n{question}\n\n"
        f"BOARD STATE\n{payload.text}\n"
    )
    schema = {
        "type": "object",
        "properties": {
            "question_id": {"type": "string"},
            "objective": {"type": "string", "enum": ["hold", "besiege", "reinforce"]},
            "actor": {"type": ["string", "null"]},
            "target": {"type": ["string", "null"]},
            "because": {"type": "string"},
        },
        "required": ["question_id", "objective", "because"],
    }
    return prompt, json.dumps(schema)


def _chat(host: str, model: str, prompt: str, schema: str) -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return one JSON object only."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": json.loads(schema),
        "options": {"temperature": 0, "num_ctx": 8192},
    }
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    message = payload.get("message") or {}
    content = message.get("content") or ""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"_raw": content, "objective": None, "target": None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument(
        "--out",
        type=Path,
        default=FIXTURE / "MODEL_COMPARISON.md",
    )
    args = parser.parse_args()
    prompt, schema = _compose_prompt()
    rows: list[str] = [
        "# F6 model comparison — Segesta fixture",
        "",
        "Temperature 0. Target: `besiege` with `target: set_segesta`.",
        "",
        "| Model | Correct / N | Notes |",
        "|---|---|---|",
    ]
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        hits = 0
        notes: list[str] = []
        for i in range(args.samples):
            try:
                answer = _chat(args.host, model, prompt, schema)
            except Exception as exc:  # noqa: BLE001
                notes.append(f"sample {i+1}: {exc}")
                break
            obj = (answer.get("objective") or "").strip().lower()
            target = (answer.get("target") or "").strip().lower()
            if obj == "besiege" and target == "set_segesta":
                hits += 1
            else:
                notes.append(f"{obj}/{target}")
        note = "; ".join(notes[:3]) if notes else "ok"
        rows.append(f"| `{model}` | {hits} / {args.samples} | {note} |")
        print(f"{model}: {hits}/{args.samples}")
    rows.append("")
    rows.append(
        "Shipping choice is section 6 — do not pin the overlay from this table alone."
    )
    args.out.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
