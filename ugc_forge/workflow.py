from __future__ import annotations
from pathlib import Path
import json
from . import jobs

# The creative stage the project is in, and which stages the user has approved. SKILL.md uses the same
# names; the agent changes this file only through `ugc-forge stage` and `ugc-forge approve`.
STAGES = [
    "source", "avatar_design", "avatar_review", "concept", "beats", "prompt_review", "calibration",
    "preflight", "cost_approval", "a_roll_generation", "b_roll_generation", "complete",
]

def default() -> dict:
    return {"stage": "source", "approved": {s: False for s in STAGES}}

def path(project: Path) -> Path:
    return project / "workflow.json"

def load(project: Path) -> dict:
    p = path(project)
    state = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    # Older projects used other layouts; keep any approvals whose names still exist.
    out = default()
    if state.get("stage") in STAGES: out["stage"] = state["stage"]
    for k, v in (state.get("approved") or {}).items():
        if k in STAGES: out["approved"][k] = bool(v)
    return out

def save(project: Path, state: dict):
    jobs.write_json(path(project), state)

def _check(stage: str):
    if stage not in STAGES:
        raise ValueError(f"Unknown stage '{stage}'. Stages: {', '.join(STAGES)}")

def _update(project: Path, change) -> dict:
    # Normalise older layouts first, then change and save under the file's lock.
    def apply(data):
        fresh = load(project); change(fresh); data.clear(); data.update(fresh)
    return jobs.update_json(path(project), apply, default)

def set_stage(project: Path, stage: str) -> dict:
    _check(stage)
    return _update(project, lambda st: st.__setitem__("stage", stage))

def approve(project: Path, stage: str, approved: bool = True) -> dict:
    _check(stage)
    return _update(project, lambda st: st["approved"].__setitem__(stage, approved))
