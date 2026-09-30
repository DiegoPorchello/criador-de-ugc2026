from __future__ import annotations
from pathlib import Path
import json, hashlib
from .timing import choose_duration
from .providers import validate_video_config
from . import jobs
from .storyboard import load as load_beats, generation_beats, beat_id as _beat_id

def path(project: Path): return project/"calibration.json"

def load(project: Path):
    p=path(project)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {
        "status":"not_started","beat_id":None,"attempts":[],"locked":False,
        "locked_prompt_hash":None
    }

def _default() -> dict:
    return {"status":"not_started","beat_id":None,"attempts":[],"locked":False,"locked_prompt_hash":None}

def update(project: Path, change) -> dict:
    """Change calibration.json under its lock, merging into whatever is there now."""
    return jobs.update_json(path(project),change,_default)

def prompt_hash(scene: str, fixed: str) -> str:
    return hashlib.sha256((scene+"\n---DIALOGUE---\n"+fixed).encode()).hexdigest()

def compose(scene: str, beat: dict, fixed: str) -> str:
    # Consistency default: only dialogue changes. prompt_override is deliberately exceptional.
    parts=[scene.rstrip(), f'"{beat["dialogue"].strip()}"']
    override=beat.get("prompt_override")
    if override: parts.append("Intentional beat-specific override:\n"+override.strip())
    parts.append(fixed.lstrip())
    return "\n\n".join(parts).strip()

def select_beat(project: Path,cfg: dict,beat_id: str|None=None) -> tuple[str,dict]:
    """(id, beat) for the line to calibrate, named the same way the storyboard names it."""
    beats=load_beats(project,cfg); spoken={id(b) for b in generation_beats(beats)}
    candidates=[(_beat_id(b,i),b) for i,b in enumerate(beats,1) if id(b) in spoken]
    if not candidates: raise RuntimeError("No avatar/dialogue beats available for calibration.")
    requested=beat_id or cfg["generation"].get("calibration_beat_id")
    if requested:
        for bid,b in candidates:
            if bid==requested: return bid,b
        raise RuntimeError(f"Calibration beat not found: {requested}. Spoken beats: {', '.join(x for x,_ in candidates)}.")
    # First avatar beat is a safe default; agent/user can explicitly select another representative beat.
    return candidates[0]

def generate(project: Path,cfg: dict,beat_id: str|None=None):
    validate_video_config(cfg)
    if load(project).get("locked"): raise RuntimeError("Calibration is locked. Unlock it before regenerating.")
    bid,beat=select_beat(project,cfg,beat_id)
    # One calibration run at a time per project; it can wait on a provider's queue for a long while.
    with jobs.file_lock(path(project),name="run",stale_after=jobs.IMAGE_LOCK_STALE_AFTER):
        return _generate(project,cfg,bid,beat)

def _generate(project: Path,cfg: dict,bid: str,beat: dict):
    state=load(project)
    ref=project/cfg["paths"]["avatar_reference"]
    if not ref.exists(): raise FileNotFoundError(f"Missing avatar reference image: {ref}")
    scene=(project/cfg["paths"]["scene_prompt"]).read_text(encoding="utf-8")
    fixed=(project/cfg["paths"]["fixed_rules_prompt"]).read_text(encoding="utf-8")
    try: natural,duration=choose_duration(beat["dialogue"],cfg["timing"],beat.get("duration"))
    except ValueError as e: raise ValueError(f"{bid}: {e}") from e
    prompt=compose(scene,beat,fixed); ref_sha=jobs.file_sha256(ref)
    fp=jobs.video_fingerprint(cfg,prompt,ref_sha,duration)
    last=state["attempts"][-1] if state["attempts"] else None
    # An interrupted attempt with the same inputs is collected rather than paid for again.
    resume=last if last and last.get("status")=="pending" and last.get("fingerprint")==fp else None
    attempt=resume["attempt"] if resume else len(state["attempts"])+1
    outdir=project/cfg["paths"]["output"]/"calibration"; outdir.mkdir(parents=True,exist_ok=True)
    outfile=outdir/f"{bid}_attempt-{attempt:02d}.mp4"
    extra={"attempt":attempt,"beat_id":bid,"output":outfile.relative_to(project).as_posix(),"fingerprint":fp,
           "prompt_hash":prompt_hash(scene,fixed),"reference_sha256":ref_sha}
    def persist(rec):
        # Merge only this attempt into the latest file, so a lock-prompt or abandon made meanwhile survives.
        def change(st):
            at=[i for i,a in enumerate(st["attempts"]) if a.get("attempt")==attempt]
            if at: st["attempts"][at[0]]=rec
            else: st["attempts"].append(rec)
        update(project,change)
    rec=jobs.run_clip(prompt,ref,cfg,duration,outfile,resume or {},persist,extra)
    persist(rec)
    if rec["status"]!="success":
        raise RuntimeError(f"Calibration attempt {attempt} did not produce a clip: {rec.get('error')}"
                           +(" Rerun the same command to collect it without paying again." if rec["status"]=="pending" else ""))
    def reviewed(st):
        st["beat_id"]=bid
        if not st.get("locked"): st["status"]="review"
    update(project,reviewed)
    return rec

def _succeeded(state: dict) -> list[dict]:
    # Attempts recorded before status tracking existed were only saved on success.
    return [a for a in state["attempts"] if a.get("status","success")=="success"]

def lock(project: Path,cfg: dict,attempt: int|None=None):
    out={}
    def change(state):
        out.update(_lock(project,cfg,state,attempt))
    update(project,change)
    return out

def _lock(project: Path,cfg: dict,state: dict,attempt: int|None) -> dict:
    done=_succeeded(state)
    if not done: raise RuntimeError("Generate at least one calibration clip before locking.")
    chosen=[a for a in done if a["attempt"]==attempt] if attempt else [done[-1]]
    if not chosen:
        raise RuntimeError(f"No successful calibration attempt {attempt}. Successful attempts: {', '.join(str(a['attempt']) for a in done)}.")
    chosen=chosen[0]
    scene=(project/cfg["paths"]["scene_prompt"]).read_text(encoding="utf-8")
    fixed=(project/cfg["paths"]["fixed_rules_prompt"]).read_text(encoding="utf-8")
    current=prompt_hash(scene,fixed)
    if chosen.get("prompt_hash")!=current:
        raise RuntimeError(f"The prompt files changed after calibration attempt {chosen['attempt']} was made, so no clip shows the current prompt. "
                           "Generate a new calibration clip with the current prompt, or put the prompt back, before locking.")
    ref=project/cfg["paths"]["avatar_reference"]
    ref_sha=jobs.file_sha256(ref) if ref.exists() else None
    if chosen.get("reference_sha256") and chosen["reference_sha256"]!=ref_sha:
        raise RuntimeError(f"The avatar reference image changed after calibration attempt {chosen['attempt']} was made. Generate a new calibration clip before locking.")
    state["locked"]=True; state["status"]="locked"
    state["locked_prompt_hash"]=current; state["locked_reference_sha256"]=ref_sha
    state["accepted_attempt"]=chosen["attempt"]
    return state

def unlock(project: Path):
    return update(project,lambda st: st.update(locked=False,status="review",locked_prompt_hash=None,locked_reference_sha256=None))

def assert_locked_current(project: Path,cfg: dict):
    if not cfg["generation"].get("require_calibration",True): return
    state=load(project)
    if not state.get("locked"): raise RuntimeError("Prompt calibration is not locked. Calibrate and lock before production generation.")
    scene=(project/cfg["paths"]["scene_prompt"]).read_text(encoding="utf-8")
    fixed=(project/cfg["paths"]["fixed_rules_prompt"]).read_text(encoding="utf-8")
    if state.get("locked_prompt_hash") != prompt_hash(scene,fixed):
        raise RuntimeError("Scene/fixed-rules prompt changed after calibration lock. Recalibrate or explicitly relock.")
    ref=project/cfg["paths"]["avatar_reference"]
    if state.get("locked_reference_sha256") and (not ref.exists() or jobs.file_sha256(ref)!=state["locked_reference_sha256"]):
        raise RuntimeError("The avatar reference image changed after calibration lock. Generate a new calibration clip and lock again.")
