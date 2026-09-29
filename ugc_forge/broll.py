from __future__ import annotations
from pathlib import Path
import concurrent.futures, json, threading
from .pricing import estimate_video_cost
from .providers import validate_video_config
from . import images, jobs
from .images import _rel
from .storyboard import load as load_beats, validate as validate_beats, GENERATED_BROLL

# Where a generated shot's reference image comes from when the storyboard doesn't say.
DEFAULT_INPUTS={"avatar_broll":["avatar"],"scene_broll":["source"]}

def path(project: Path) -> Path: return project/"broll.json"

def load(project: Path) -> dict:
    p=path(project)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"references":{},"clips":{}}

def save(project: Path, state: dict): jobs.write_json(path(project),state)

sha256=jobs.file_sha256


def out_dir(project: Path, cfg: dict) -> Path:
    return project/cfg["paths"].get("b_roll_output","output/b-roll")

def items(project: Path, cfg: dict) -> dict:
    """Generated B-roll beats keyed by id, with their storyboard position."""
    beats=load_beats(project,cfg); validate_beats(beats)
    out={}
    for i,b in enumerate(beats,1):
        if (b.get("overlay") or {}).get("type") in GENERATED_BROLL:
            out[b.get("id") or f"{i:02d}"]={"index":i,"beat":b}
    return out

def get_item(project: Path, cfg: dict, beat_id: str) -> dict:
    found=items(project,cfg)
    if beat_id not in found:
        names=", ".join(found) or "none"
        raise RuntimeError(f"'{beat_id}' is not a generated B-roll beat. Generated B-roll beats: {names}.")
    return found[beat_id]

def reference_path(project: Path, cfg: dict, bid: str) -> Path:
    # Named by beat id only, so inserting or reordering beats never hides an approved image.
    return out_dir(project,cfg)/"references"/f"{bid}.png"

def clip_path(project: Path, cfg: dict, index: int, bid: str) -> Path:
    return out_dir(project,cfg)/f"{index:02d}_{bid}.mp4"

def resolve_input(project: Path, cfg: dict, ref: str, found: dict) -> Path:
    if ref=="avatar": p=project/cfg["paths"]["avatar_reference"]
    elif ref=="source": p=project/cfg["paths"]["source_frame"]
    elif ref in found:
        p=reference_path(project,cfg,ref)
        if not p.exists(): raise FileNotFoundError(f"Input '{ref}' has no B-roll image yet. Make it first: ugc-forge broll-image {project} {ref}")
        return p
    else: p=Path(ref).expanduser() if Path(ref).expanduser().is_absolute() else project/ref
    if not p.exists(): raise FileNotFoundError(f"B-roll input '{ref}' not found at {p}.")
    return p

def image_request(project: Path, cfg: dict, beat_id: str, prompt: str|None=None, inputs: list[str]|None=None) -> dict:
    item=get_item(project,cfg,beat_id); ov=item["beat"]["overlay"]
    text=(prompt or ov.get("prompt") or ov.get("description") or "").strip()
    if not text: raise RuntimeError(f"{beat_id}: no image prompt. Add overlay.prompt or overlay.description, or pass --prompt.")
    refs=inputs if inputs is not None else (ov["inputs"] if "inputs" in ov else DEFAULT_INPUTS[ov["type"]])
    found=items(project,cfg)
    return {"id":beat_id,"prompt":text,"inputs":refs,
            "paths":[resolve_input(project,cfg,r,found) for r in refs]}

def _update(project: Path, change) -> dict:
    return jobs.update_json(path(project),change,lambda: {"references":{},"clips":{}})

def make_image(project: Path, cfg: dict, beat_id: str, prompt: str|None=None, inputs: list[str]|None=None) -> dict:
    req=image_request(project,cfg,beat_id,prompt,inputs); bid=req["id"]
    # One image per shot at a time; other shots can be made in parallel. Only this shot's record is saved,
    # merged into the latest file, so parallel commands never drop each other's records.
    with jobs.file_lock(path(project),name=f"image-{bid}",stale_after=jobs.IMAGE_LOCK_STALE_AFTER):
        entry=load(project)["references"].get(bid) or {"attempts":[]}
        current=reference_path(project,cfg,bid)
        result=images.new_version(project,cfg,entry,current,current.parent/"history",bid,req["inputs"],req["paths"],
                                  req["prompt"],aspect_ratio=cfg["video"]["aspect_ratio"],model_key="broll_image")
        _update(project,lambda st: st["references"].__setitem__(bid,entry))
    return result

def use_image(project: Path, cfg: dict, beat_id: str, attempt_no: int) -> dict:
    get_item(project,cfg,beat_id); out={}
    def change(st):
        entry=st["references"].setdefault(beat_id,{"attempts":[]})
        out.update(images.use_version(project,entry,reference_path(project,cfg,beat_id),attempt_no,beat_id))
    # Same per-shot lock as make_image, so switching versions never races an image being made.
    with jobs.file_lock(path(project),name=f"image-{beat_id}",stale_after=jobs.IMAGE_LOCK_STALE_AFTER):
        _update(project,change)
    return out

def stale_inputs(project: Path, cfg: dict, state: dict, bid: str, found: dict) -> list[str]:
    """Inputs that have changed since this shot's current image was made from them."""
    entry=state["references"].get(bid) or {}
    cur=[a for a in entry.get("attempts",[]) if a["attempt"]==entry.get("current_attempt")]
    changed=[]
    for rec in (cur[0].get("inputs",[]) if cur else []):
        if rec["ref"]==bid: continue
        try: p=resolve_input(project,cfg,rec["ref"],found)
        except FileNotFoundError: changed.append(rec["ref"]); continue
        if sha256(p)!=rec["sha256"]: changed.append(rec["ref"])
    return changed

def plan(project: Path, cfg: dict, only: list[str]|None=None, redo: list[str]|None=None) -> dict:
    validate_video_config(cfg)
    found=items(project,cfg)
    unknown=[x for x in (only or [])+(redo or []) if x not in found]
    if unknown: raise RuntimeError(f"Not generated B-roll beats: {', '.join(unknown)}.")
    limit=set(only or [])|set(redo or [])
    state=load(project); supported=[int(x) for x in cfg["timing"]["supported_durations"]]
    default_d=int(cfg.get("broll",{}).get("default_duration",4))
    default_anim=cfg.get("broll",{}).get("default_animation_prompt","")
    rows=[]; stills=[]
    for bid,item in found.items():
        if limit and bid not in limit: continue
        ov=item["beat"]["overlay"]
        if ov.get("animate") is False:
            # An image used as a still in the edit; never animated.
            stills.append({"id":bid,"has_image":reference_path(project,cfg,bid).exists()}); continue
        d=int(ov.get("duration",default_d))
        if d not in supported: raise ValueError(f"{bid}: B-roll duration {d}s unsupported. Supported: {supported}")
        ref=reference_path(project,cfg,bid); out=clip_path(project,cfg,item["index"],bid)
        record=state["clips"].get(bid,{})
        ref_sha=sha256(ref) if ref.exists() else None
        anim=(ov.get("animation_prompt") or default_anim).strip()
        fp=jobs.video_fingerprint(cfg,anim,ref_sha,d)
        if ref_sha is None: status="no image"
        elif not (redo and bid in redo) and jobs.is_done(project,record,fp): status="done"
        elif record.get("status")=="pending" and record.get("fingerprint")==fp: status="in flight"
        else: status="to generate"
        if status=="in flight" and redo and bid in redo:
            raise RuntimeError(f"'{bid}' has a job in progress. Wait for it, or run `ugc-forge abandon {project} {bid}` first.")
        rows.append({"id":bid,"index":item["index"],"type":ov["type"],"duration":d,"animation_prompt":anim,
                     "reference":ref,"reference_sha256":ref_sha,"fingerprint":fp,"output":out,"status":status,
                     "done":status=="done",
                     "stale_inputs":stale_inputs(project,cfg,state,bid,found) if ref.exists() else []})
    pending=[r for r in rows if not r["done"]]
    # A clip already in flight has been paid for; collecting it costs nothing more.
    seconds=sum(r["duration"] for r in pending if r["status"] in ("to generate","no image"))
    return {"rows":rows,"pending":pending,"stills":stills,"missing":[r["id"] for r in rows if r["reference_sha256"] is None],
            "seconds":seconds,"cost":estimate_video_cost(cfg,[r["duration"] for r in pending if r["status"] in ("to generate","no image")])}

def animate(project: Path, cfg: dict, only: list[str]|None=None, on_result=None, redo: list[str]|None=None) -> dict:
    p=plan(project,cfg,only,redo)
    if p["missing"]:
        raise RuntimeError("These B-roll shots have no image yet: "+", ".join(p["missing"])
                           +f". Make each with: ugc-forge broll-image {project} BEAT_ID")
    state=load(project); lock=threading.Lock()
    def persist(bid,record):
        with lock:
            if on_result and record.get("status")=="pending" and state["clips"].get(bid,{}).get("interaction_id")!=record.get("interaction_id"):
                on_result(bid,{**record,"status":"submitted","error":None})
            state["clips"][bid]=record
            _update(project,lambda st: st["clips"].__setitem__(bid,record))
    done=[r for r in p["rows"] if r["done"]]
    for r in done: jobs.place_output(project,state["clips"][r["id"]],r["output"])
    if done: _update(project,lambda st: st["clips"].update({r["id"]:state["clips"][r["id"]] for r in done}))
    def worker(r):
        extra={"fingerprint":r["fingerprint"],"output":_rel(project,r["output"]),
               "reference_sha256":r["reference_sha256"],"animation_prompt":r["animation_prompt"]}
        retry=(lambda msg: on_result(r["id"],{"status":"retrying","error":msg})) if on_result else None
        return r["id"],jobs.run_clip(r["animation_prompt"],r["reference"],cfg,r["duration"],r["output"],
                                     state["clips"].get(r["id"],{}),lambda rec: persist(r["id"],rec),extra,on_retry=retry)
    with concurrent.futures.ThreadPoolExecutor(max_workers=int(cfg["generation"]["concurrency"])) as ex:
        for fut in concurrent.futures.as_completed([ex.submit(worker,r) for r in p["pending"]]):
            bid,result=fut.result(); persist(bid,result)
            if on_result: on_result(bid,result)
    return state
