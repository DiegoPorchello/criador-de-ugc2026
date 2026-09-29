from __future__ import annotations
from pathlib import Path
from .pricing import estimate_video_cost, reported_usd, _priced
from . import aroll, avatar, broll, calibration, jobs, sequential

# costs.json is rebuilt from the state files after every chargeable command, so it always covers all
# spend in the project: calibration, A-roll (batch and one at a time), B-roll video and every image.

NOTE=("Estimates from the configured pricing snapshot, not provider invoices. 'reported' figures use the "
      "tokens the API returned and are null if any item lacks them. Jobs that failed are not counted.")

def _video(cfg: dict, records: list[dict]) -> dict:
    ok=[r for r in records if r.get("status","success")=="success"]
    durations=[int(r.get("duration",0)) for r in ok]
    tokens=[(r.get("meta") or {}).get("video_output_tokens") for r in ok]
    usd=[reported_usd(cfg,r.get("meta"),"video") for r in ok]
    # Each clip is priced by the provider that made it; the estimate uses the current provider's rates.
    return {"clips":len(ok),"generated_seconds":sum(durations),"calculated_cost":estimate_video_cost(cfg,durations),
            "reported_video_output_tokens":sum(tokens) if tokens and None not in tokens else None,
            "reported_cost":_priced(cfg["cost"],sum(usd)) if usd and None not in usd else None}

def _images(cfg: dict, attempts: list[dict]) -> dict:
    made=[a for a in attempts if a.get("prompt") is not None]  # adopted or copied images cost nothing
    usd=[reported_usd(cfg,a.get("meta"),"image") for a in made]
    return {"images":len(made),"reported_cost":_priced(cfg["cost"],sum(usd)) if usd and None not in usd else None}

def _with_history(records) -> list[dict]:
    """Each record plus the earlier jobs it replaced (a --redo, or an abandoned job), which may have been paid for."""
    out=[]
    for r in records: out.append(r); out.extend(r.get("paid_before",[]))
    return out

def refresh(project: Path, cfg: dict) -> dict:
    job=_with_history(aroll.load(project)["clips"].values())
    seq=[a for c in sequential.load_session(project)["clips"].values() for a in c.get("attempts",[])]
    b=broll.load(project); bclips=_with_history(b["clips"].values())
    image_attempts=[a for e in b["references"].values() for a in e.get("attempts",[])]+avatar.load(project)["attempts"]
    data={
        "calibration":_video(cfg,calibration.load(project)["attempts"]),
        # Clips accepted one at a time are counted under one_at_a_time, where every attempt was paid for, and a
        # reused calibration take under calibration; neither is counted again here.
        "a_roll":_video(cfg,[c for c in job if c.get("source") not in ("sequential","calibration")]),
        "one_at_a_time":_video(cfg,seq),
        "b_roll":_video(cfg,bclips),
        "images":_images(cfg,image_attempts),
    }
    # Sections with no clips add nothing; estimate only where the provider reported no cost.
    video=[v.get("reported_cost") or v["calculated_cost"] for k,v in data.items() if k!="images" and v["clips"]]
    images=data["images"]["reported_cost"]
    total=sum(c["usd"] or 0 for c in video)+(images["usd"] if images else 0)
    # complete is False when some spend could not be priced, so the total is a lower bound.
    complete=all(c["priced"] for c in video) and (images is not None or data["images"]["images"]==0)
    data["total"]={"cost":_priced(cfg["cost"],total),"complete":complete}
    # Jobs submitted but not yet collected. kie.ai takes credits when a job starts; Google bills on completion.
    everything=job+seq+bclips+calibration.load(project)["attempts"]
    pending=[r for r in everything if r.get("status")=="pending"]
    data["in_flight"]={"clips":len(pending),"estimated_cost":estimate_video_cost(cfg,[int(r.get("duration",0)) for r in pending])}
    # Abandoned jobs can't be cancelled: kie.ai keeps the charge unless the job fails. Shown apart from the total.
    gone=[r for r in everything if r.get("status")=="abandoned"]
    data["abandoned"]={"jobs":len(gone),"possible_cost":estimate_video_cost(cfg,[int(r.get("duration",0)) for r in gone])}
    data["note"]=NOTE
    with jobs.file_lock(project/"costs.json"):
        jobs.write_json(project/"costs.json",data)
    return data
