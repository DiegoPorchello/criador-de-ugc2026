from __future__ import annotations
from pathlib import Path
import json, shutil
from .timing import choose_duration, pacing_warning
from .pricing import estimate_video_cost
from .providers import validate_video_config
from .storyboard import load as load_storyboard, validate as validate_storyboard, generation_beats
from .calibration import compose as compose_prompt, load as load_calibration
from . import jobs

# job.json is the single record of finished A-roll clips, whether made in batch or accepted one at a time.
def path(project: Path) -> Path: return project/"job.json"

def load(project: Path) -> dict:
    p=path(project)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"clips":{}}

def save(project: Path, state: dict): jobs.write_json(path(project),state)

def update(project: Path, change) -> dict:
    """Change job.json under its lock, so parallel commands never overwrite each other's clips."""
    return jobs.update_json(path(project),change,lambda: {"clips":{}})

def _calibration_take(project: Path) -> dict|None:
    cal=load_calibration(project)
    if not cal.get("locked"): return None
    take=[a for a in cal["attempts"] if a.get("attempt")==cal.get("accepted_attempt") and a.get("status","success")=="success"]
    return take[0] if take and (project/take[0]["output"]).exists() else None

def adopt_calibration(project: Path, row: dict) -> dict:
    """Use the approved calibration take as this line's finished clip instead of paying for it again."""
    take=_calibration_take(project)
    row["output"].parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(project/take["output"],row["output"])
    rec={"status":"success","fingerprint":row["fingerprint"],"content_fingerprint":row["content_fingerprint"],"duration":take["duration"],"output":str(row["output"].relative_to(project)),
         "attempts":0,"source":"calibration","calibration_attempt":take["attempt"],"provider":take.get("provider"),"meta":take.get("meta",{})}
    update(project,lambda st: st["clips"].__setitem__(row["id"],rec))
    return rec

def out_dir(project: Path, cfg: dict) -> Path:
    return project/cfg["paths"].get("a_roll_output",cfg["paths"]["output"])

def load_beats(project: Path, cfg: dict) -> list[dict]:
    beats=load_storyboard(project,cfg); validate_storyboard(beats); return beats

def plan(project: Path, cfg: dict, redo: list[str]|None=None) -> dict:
    """Every spoken A-roll beat, whether its clip is already done, and the cost of the rest."""
    validate_video_config(cfg); rows=[]
    all_beats=load_beats(project,cfg)
    ids=[b.get("id") or f"{i:02d}" for i,b in enumerate(all_beats,1)]
    unknown=[x for x in (redo or []) if x not in ids]
    if unknown: raise RuntimeError(f"Not beats in this storyboard: {', '.join(unknown)}.")
    avatar_ids={id(b) for b in generation_beats(all_beats)}
    ref=project/cfg["paths"]["avatar_reference"]
    ref_sha=jobs.file_sha256(ref) if ref.exists() else None
    pre=(project/cfg["paths"]["scene_prompt"]).read_text(encoding="utf-8"); post=(project/cfg["paths"]["fixed_rules_prompt"]).read_text(encoding="utf-8")
    clips=load(project)["clips"]; outdir=out_dir(project,cfg); take=_calibration_take(project)
    for i,b in enumerate(all_beats,1):
        if id(b) not in avatar_ids: continue
        bid=ids[i-1]
        if redo and bid not in redo: continue
        try: req,d=choose_duration(b["dialogue"],cfg["timing"],b.get("duration"))
        except ValueError as e: raise ValueError(f"{bid}: {e}") from e
        prompt=compose_prompt(pre,b,post); fp=jobs.video_fingerprint(cfg,prompt,ref_sha,d)
        cfp=jobs.content_fingerprint(cfg,prompt,ref_sha)
        record=clips.get(bid,{})
        # An explicit duration in the storyboard is a deliberate choice, so only an exact match counts then.
        loose=b.get("duration") is None
        done=not redo and cfg["generation"]["resume"] and jobs.is_done(project,record,fp,cfp if loose else None,req)
        status="done" if done else ("in flight" if record.get("status")=="pending" and record.get("fingerprint")==fp else "to generate")
        if status=="in flight" and redo:
            raise RuntimeError(f"'{bid}' has a job in progress. Wait for it, or run `ugc-forge abandon {project} {bid}` first.")
        # The approved calibration take is this exact clip when nothing about the line has changed since.
        if status=="to generate" and not redo and take and take.get("beat_id")==bid and take.get("fingerprint")==fp: status="from calibration"
        rows.append({"index":i,"id":bid,"beat":b,"dialogue":b["dialogue"],"prompt":prompt,"fingerprint":fp,"content_fingerprint":cfp,"status":status,
                     "output":outdir/f"{i:02d}_{bid}.mp4","estimated_natural_seconds":round(req,2),"duration":d,
                     "pacing_warning":pacing_warning(req,d,cfg["timing"])})
    pending=[r for r in rows if r["status"]!="done"]
    # A clip already in flight has been paid for; collecting it costs nothing more.
    seconds=sum(r["duration"] for r in pending if r["status"]=="to generate")
    return {"rows":rows,"pending":pending,"seconds":seconds,
            "cost":estimate_video_cost(cfg,[r["duration"] for r in pending if r["status"]=="to generate"])}

