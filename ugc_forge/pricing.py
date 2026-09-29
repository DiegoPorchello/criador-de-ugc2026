from __future__ import annotations

def _unpriced(reason: str) -> dict:
    return {"priced": False, "usd": None, "display": "unpriced", "reason": reason}

def _kie_video(cfg: dict, durations: list[int]) -> dict:
    resolution = str(cfg["video"]["resolution"]).lower()
    kie = cfg["cost"].get("kie") or {}
    table = (kie.get("video_credits") or {}).get(resolution) or {}
    table = {int(k): v for k, v in table.items()}
    missing = sorted({d for d in durations if d not in table})
    if missing or kie.get("usd_per_credit") is None:
        return _unpriced(f"No kie.ai price configured for {resolution} {', '.join(f'{d}s' for d in missing)} clips.".replace("  ", " "))
    return _priced(cfg["cost"], sum(table[d] for d in durations) * float(kie["usd_per_credit"]))

def estimate_video_cost(cfg: dict, durations) -> dict:
    """Estimated cost of generating clips of these durations (a single duration or a list)."""
    ds = [int(durations)] if isinstance(durations, (int, float)) else [int(d) for d in durations]
    if (cfg.get("provider") or "kie") == "kie":
        return _kie_video(cfg, ds)
    seconds = sum(ds)
    resolution = str(cfg["video"]["resolution"]).lower()
    cost = cfg["cost"]
    base = cost.get("usd_per_second_720p")
    mult = (cost.get("resolution_multipliers") or {}).get(resolution)
    if base is None or mult is None:
        return _unpriced(f"No verified pricing configured for {resolution}.")
    return _priced(cost, float(base) * float(mult) * seconds)

def video_cost_from_tokens(cfg: dict, tokens: int) -> dict:
    rate = cfg["cost"].get("usd_per_million_video_output_tokens")
    if rate is None:
        return _unpriced("No usd_per_million_video_output_tokens configured.")
    return _priced(cfg["cost"], float(rate) * tokens / 1_000_000)

def image_cost_from_tokens(cfg: dict, model: str, tokens: int|None) -> dict:
    rate = (cfg["cost"].get("image_usd_per_million_output_tokens") or {}).get(model)
    if rate is None or tokens is None:
        return _unpriced(f"No image pricing configured for {model}." if rate is None else "No token count reported.")
    return _priced(cfg["cost"], float(rate) * tokens / 1_000_000)

def estimate_image_cost(cfg: dict, model_key: str = "image") -> dict:
    if (cfg.get("provider") or "kie") == "kie":
        kie = cfg["cost"].get("kie") or {}
        if kie.get("image_credits") is None or kie.get("usd_per_credit") is None:
            return _unpriced("No kie.ai image price configured.")
        return _priced(cfg["cost"], float(kie["image_credits"]) * float(kie["usd_per_credit"]))
    model = cfg["generation_models"][model_key]["model"]
    return image_cost_from_tokens(cfg, model, cfg["cost"].get("estimated_image_output_tokens"))

def reported_usd(cfg: dict, meta: dict, kind: str) -> float | None:
    """What the provider says a finished job cost: kie.ai credits, or Google tokens. None if unknown."""
    meta = meta or {}
    if meta.get("credits") is not None:
        rate = (cfg["cost"].get("kie") or {}).get("usd_per_credit")
        return float(meta["credits"]) * float(rate) if rate is not None else None
    if kind == "video" and meta.get("video_output_tokens") is not None:
        return video_cost_from_tokens(cfg, meta["video_output_tokens"]).get("usd")
    if kind == "image" and meta.get("image_output_tokens") is not None:
        return image_cost_from_tokens(cfg, meta.get("model") or cfg["generation_models"]["image"]["model"], meta["image_output_tokens"]).get("usd")
    return None

def _priced(cost: dict, usd: float) -> dict:
    gbp_rate = cost.get("gbp_per_usd")
    currency = str(cost.get("currency", "USD")).upper()
    if currency == "GBP" and gbp_rate:
        amount = usd * float(gbp_rate)
        return {"priced": True, "usd": usd, "amount": amount, "currency": "GBP", "display": f"£{amount:.2f}"}
    return {"priced": True, "usd": usd, "amount": usd, "currency": "USD", "display": f"${usd:.2f}"}
