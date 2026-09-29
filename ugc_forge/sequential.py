from __future__ import annotations
from pathlib import Path
import json, shutil
from .pricing import estimate_video_cost
from .providers import validate_video_config
from . import aroll, jobs
from .calibration import assert_locked_current

# One-at-a-time A-roll. Attempts are kept in sequential.json and output/a-roll/attempts/; accepting one
# copies it to the same final file batch mode uses and records it in job.json, so both modes agree on
# which lines are finished.

def session_path(project: Path) -> Path:
    return project/"sequential.json"

def load_session(project: Path) -> dict:
    p=session_path(project)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"mode":"sequential","clips":{}}

def save_session(project: Path, state: dict):
    jobs.write_json(session_path(project),state)

def current(project: Path, cfg: dict):
    """The first spoken beat, in storyboard order, without a current finished clip."""
    state=load_session(project)
    pending=aroll.plan(project,cfg)["pending"]
    while pending and pending[0]["status"]=="from calibration":
        aroll.adopt_calibration(project,pending.pop(0))  # already approved and paid for as the calibration take
    if not pending: return None,state
    item=pending[0]
    return {**item,"estimated_cost":estimate_video_cost(cfg,item["duration"])},state

def _attempt_file(project: Path, cfg: dict, item: dict, n: int) -> Path:
    return aroll.out_dir(project,cfg)/"attempts"/f"{item['index']:02d}_{item['id']}_attempt-{n:02d}.mp4"

def generate_current(project: Path, cfg: dict):
    validate_video_config(cfg); assert_locked_current(project,cfg)
    # One line at a time per project; a job can wait on a provider's queue for a long while.
    with jobs.file_lock(session_path(project),name="run",stale_after=jobs.IMAGE_LOCK_STALE_AFTER):
        return _generate_current(project,cfg)

def _generate_current(project: Path, cfg: dict):
    item,state=current(project,cfg)
    if item is None: raise RuntimeError("Sequential session is already complete.")
    bid=item["id"]; ref=project/cfg["paths"]["avatar_reference"]
    if not ref.exists(): raise FileNotFoundError(f"Missing avatar reference image: {ref}")
    entry=state["clips"].setdefault(bid,{"attempts":[]})
    last=entry["attempts"][-1] if entry["attempts"] else None
    # An interrupted attempt with the same inputs is collected rather than paid for again.
    resume=last if last and last.get("status")=="pending" and last.get("fingerprint")==item["fingerprint"] else None
    attempt_no=resume["attempt"] if resume else len(entry["attempts"])+1
    outfile=_attempt_file(project,cfg,item,attempt_no)
    def persist(rec):
        # Merge only this attempt into the latest file, so an abandon made meanwhile survives.
        def change(st):
            att=st["clips"].setdefault(bid,{"attempts":[]})["attempts"]
            at=[i for i,a in enumerate(att) if a.get("attempt")==attempt_no]
            if at: att[at[0]]=rec
            else: att.append(rec)
        jobs.update_json(session_path(project),change,lambda: {"mode":"sequential","clips":{}})
    rec=jobs.run_clip(item["prompt"],ref,cfg,item["duration"],outfile,resume or {},persist,
                      {"attempt":attempt_no,"output":str(outfile.relative_to(project)),"fingerprint":item["fingerprint"]})
    persist(rec)
    if rec["status"]!="success":
        raise RuntimeError(f"{bid} attempt {attempt_no} did not produce a clip: {rec.get('error')}"
                           +(" Rerun the same command to collect it without paying again." if rec["status"]=="pending" else ""))
    return item,rec

def accept_current(project: Path, cfg: dict, attempt_no: int|None=None):
    item,state=current(project,cfg)
    if item is None: raise RuntimeError("Sequential session is already complete.")
    ok=[a for a in state["clips"].get(item["id"],{}).get("attempts",[])
        if a.get("status")=="success" and a.get("fingerprint")==item["fingerprint"] and (project/a["output"]).exists()]
    if not ok:
        raise RuntimeError(f"No attempt of '{item['id']}' matches its current line and setup. Generate it first.")
    chosen=[a for a in ok if a["attempt"]==attempt_no] if attempt_no else [ok[-1]]
    if not chosen:
        raise RuntimeError(f"Attempt {attempt_no} of '{item['id']}' can't be accepted. Usable attempts: {', '.join(str(a['attempt']) for a in ok)}.")
    chosen=chosen[0]
    item["output"].parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(project/chosen["output"],item["output"])
    rec={"status":"success","fingerprint":item["fingerprint"],"content_fingerprint":item["content_fingerprint"],"duration":chosen["duration"],
         "output":str(item["output"].relative_to(project)),"attempts":len(ok),
         "accepted_attempt":chosen["attempt"],"source":"sequential","meta":chosen.get("meta",{})}
    aroll.update(project,lambda st: st["clips"].__setitem__(item["id"],rec))
    return current(project,cfg)
