from __future__ import annotations
from pathlib import Path
import json

# Generated types are made by Forge; the rest are assets supplied for the edit.
GENERATED_BROLL={"avatar_broll","scene_broll"}
VALID_OVERLAYS={"broll","avatar_broll","scene_broll","still","graphic","other"}

def load(project: Path, cfg: dict) -> list[dict]:
    path=project/cfg["paths"]["beats"]
    if not path.exists(): raise FileNotFoundError(f"No storyboard at {path}.")
    try: beats=json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e: raise ValueError(f"{path} is not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}.") from e
    if not isinstance(beats,list): raise ValueError("beats.json must be a JSON array.")
    return beats

def validate(beats: list[dict]):
    ids=set()
    for i,b in enumerate(beats,1):
        bid=b.get("id") or f"{i:02d}"
        if bid in ids: raise ValueError(f"Duplicate beat id: {bid}")
        ids.add(bid)
        if b.get("a_roll", True) and not b.get("dialogue"):
            raise ValueError(f"{bid}: A-roll beat requires dialogue.")
        overlay=b.get("overlay")
        if overlay is not None:
            if not isinstance(overlay,dict): raise ValueError(f"{bid}: overlay must be an object.")
            typ=overlay.get("type")
            if typ not in VALID_OVERLAYS: raise ValueError(f"{bid}: invalid overlay type {typ}")
            if typ in GENERATED_BROLL:
                if not (overlay.get("description") or overlay.get("prompt")):
                    raise ValueError(f"{bid}: {typ} requires a description or prompt.")
                inputs=overlay.get("inputs")
                # An empty list means the image is made from the description alone (a new scene).
                if inputs is not None and not (isinstance(inputs,list) and all(isinstance(x,str) and x.strip() for x in inputs)):
                    raise ValueError(f"{bid}: overlay.inputs must be a list of image references ([] for none).")
                if "animate" in overlay and not isinstance(overlay["animate"],bool):
                    raise ValueError(f"{bid}: overlay.animate must be true or false.")
                if "duration" in overlay and not isinstance(overlay["duration"],int):
                    raise ValueError(f"{bid}: overlay.duration must be a whole number of seconds.")
    return True

def beat_id(beat: dict, position: int) -> str:
    """A beat's id: its own, or its 1-based position ("01") when it has none. Used everywhere a beat is named."""
    return beat.get("id") or f"{position:02d}"

def generation_beats(beats: list[dict]):
    # v1 uses full A-roll: every spoken beat is generated unless explicitly disabled.
    return [b for b in beats if b.get("a_roll",True) and b.get("dialogue")]

def storyboard_rows(beats: list[dict]):
    rows=[]
    for i,b in enumerate(beats,1):
        overlay=b.get("overlay") or {}
        rows.append({
            "index":i,
            "id":b.get("id") or f"{i:02d}",
            "spoken":b.get("dialogue",""),
            "a_roll":b.get("a_roll",True),
            "overlay":overlay.get("type",""),
            "on_screen":overlay.get("description") or overlay.get("asset") or "A-roll presenter",
        })
    return rows
