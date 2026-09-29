from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from . import aroll, broll, calibration, jobs, providers, sequential

# Jobs that were submitted (and possibly paid for) but not yet collected. Abandoning one tells Forge to stop
# waiting for it, so the next run submits a new job - for example after switching provider.

PROVIDER_NAMES = {"kie": "kie.ai", "google": "Google"}

def find(project: Path) -> list[dict]:
    out = []
    for bid, r in aroll.load(project)["clips"].items():
        if r.get("status") == "pending": out.append({"kind": "A-roll", "id": bid, "record": r})
    for bid, r in broll.load(project)["clips"].items():
        if r.get("status") == "pending": out.append({"kind": "B-roll", "id": bid, "record": r})
    for a in calibration.load(project)["attempts"]:
        if a.get("status") == "pending": out.append({"kind": "calibration", "id": a.get("beat_id"), "record": a})
    for bid, c in sequential.load_session(project)["clips"].items():
        for a in c.get("attempts", []):
            if a.get("status") == "pending": out.append({"kind": "one-at-a-time", "id": bid, "record": a})
    return out

def _mark(project: Path, hit: dict):
    job_id = hit["record"]["interaction_id"]
    stamp = {"status": "abandoned", "abandoned_at": datetime.now(timezone.utc).isoformat()}
    def mark(rec):
        if rec.get("status") == "pending" and rec.get("interaction_id") == job_id: rec.update(stamp)
    if hit["kind"] == "A-roll":
        aroll.update(project, lambda st: mark(st["clips"][hit["id"]]))
    elif hit["kind"] == "B-roll":
        jobs.update_json(broll.path(project), lambda st: mark(st["clips"][hit["id"]]), lambda: {"references": {}, "clips": {}})
    elif hit["kind"] == "calibration":
        jobs.update_json(calibration.path(project), lambda st: [mark(a) for a in st["attempts"]], lambda: {"attempts": []})
    else:
        jobs.update_json(sequential.session_path(project), lambda st: [mark(a) for a in st["clips"][hit["id"]]["attempts"]],
                         lambda: {"clips": {}})

def abandon(project: Path, cfg: dict, beat_id: str, force: bool = False) -> list[dict]:
    hits = [h for h in find(project) if h["id"] == beat_id]
    if not hits:
        others = ", ".join(sorted({h["id"] for h in find(project)})) or "none"
        raise RuntimeError(f"Nothing is in progress for '{beat_id}'. Jobs in progress: {others}.")
    for h in hits:
        rec = h["record"]; prov = rec.get("provider") or providers.name(cfg)
        h["provider"] = PROVIDER_NAMES.get(prov, prov)
        h["state"] = providers.job_state(rec["interaction_id"], cfg, prov)
        if h["state"] in providers.FINISHED_STATES and not force:
            raise RuntimeError(f"The {h['kind']} job for '{beat_id}' has already finished at {h['provider']} and is paid for. "
                               "Rerun the same generate command to collect it instead of abandoning it.")
    for h in hits: _mark(project, h)
    return hits
