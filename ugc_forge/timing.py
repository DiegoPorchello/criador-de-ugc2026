from __future__ import annotations
import re

PAUSES={",":0.08,";":0.12,":":0.12,".":0.18,"!":0.18,"?":0.18,"…":0.28}

def estimate_seconds(text: str, cfg: dict) -> float:
    words=len(re.findall(r"\b[\w’'-]+\b",text))
    base=(words/max(float(cfg["words_per_minute"]),1))*60.0
    pauses=sum(text.count(k)*v for k,v in PAUSES.items())
    return base+pauses+float(cfg.get("lead_in_seconds",0))+float(cfg.get("tail_seconds",0))

def choose_duration(text: str, cfg: dict, override=None):
    supported=sorted(int(x) for x in cfg.get("supported_durations",list(range(3,11))))
    natural=estimate_seconds(text,cfg)
    if override is not None:
        d=int(override)
        if d not in supported: raise ValueError(f"Duration {d}s unsupported. Supported: {supported}")
        return natural,d
    for d in supported:
        if natural <= d: return natural,d
    raise ValueError(f"Estimated speech {natural:.1f}s exceeds maximum supported duration {max(supported)}s; split or shorten the beat.")

def pacing_warning(natural: float, duration: int, cfg: dict) -> str | None:
    # A heuristic only: the model may alter cadence based on requested duration.
    ratio=abs(duration-natural)/max(natural,0.1)
    threshold=float(cfg.get("pacing_warning_ratio",0.18))
    if ratio < threshold: return None
    if duration > natural:
        return "Selected duration is materially longer than estimated speech; delivery may slow. Consider rewriting, a disposable tail, or manual override."
    return "Selected duration is shorter than estimated speech; delivery may rush or truncate. Shorten/split the beat."
