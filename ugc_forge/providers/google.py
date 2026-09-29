from __future__ import annotations
from pathlib import Path
import base64, time
from .base import VideoJobError, image_mime_type, _write_image, resolve_key, fetch_with_retry, save_video

SUPPORTED_VIDEO_RESOLUTIONS={"360p","720p","1080p","4k"}
SUPPORTED_VIDEO_ASPECTS={"16:9","9:16"}
SUPPORTED_IMAGE_MODELS={"gemini-3-pro-image","gemini-3.1-flash-image"}
SUPPORTED_VIDEO_MODEL="gemini-omni-1.1-flash"
# Google documents 3-10 s; 3, 4, 5, 6, 7 and 10 were confirmed live on 2026-09-28.
SUPPORTED_VIDEO_DURATIONS=set(range(3,11))

def validate_generation_models(cfg):
    video_model=cfg["generation_models"]["video"]["model"]
    for key in ("image","broll_image"):
        image_model=cfg["generation_models"][key]["model"]
        if image_model not in SUPPORTED_IMAGE_MODELS:
            raise ValueError(f"Unsupported {key} model: {image_model}. This release supports {', '.join(sorted(SUPPORTED_IMAGE_MODELS))}.")
    if video_model != SUPPORTED_VIDEO_MODEL:
        raise ValueError(
            f"Unsupported video model: {video_model}. "
            f"This release supports only {SUPPORTED_VIDEO_MODEL}."
        )

def validate_video_config(cfg):
    validate_generation_models(cfg)
    res=str(cfg["video"]["resolution"]).lower()
    ar=str(cfg["video"]["aspect_ratio"])
    if res not in SUPPORTED_VIDEO_RESOLUTIONS: raise ValueError(f"Unsupported resolution: {res}")
    if ar not in SUPPORTED_VIDEO_ASPECTS: raise ValueError(f"Unsupported aspect ratio: {ar}")
    durations={int(x) for x in cfg["timing"].get("supported_durations",sorted(SUPPORTED_VIDEO_DURATIONS))}
    if not durations or not durations <= SUPPORTED_VIDEO_DURATIONS:
        raise ValueError(f"Pinned Omni workflow supports durations {sorted(SUPPORTED_VIDEO_DURATIONS)}.")

def resolve_api_key(provider_cfg):
    return resolve_key(provider_cfg, "Google")

def _client(provider_cfg):
    from google import genai
    return genai.Client(api_key=resolve_api_key(provider_cfg))

def _image_output_tokens(response):
    # Count image tokens only: the candidate total also includes any text the model returns.
    usage=getattr(response,"usage_metadata",None)
    for d in getattr(usage,"candidates_tokens_details",None) or []:
        if "IMAGE" in str(getattr(d,"modality","")).upper(): return getattr(d,"token_count",None)
    return getattr(usage,"candidates_token_count",None)

def generate_image(inputs: list[Path], prompt: str, cfg: dict, output: Path, aspect_ratio: str|None=None, model_key: str="image") -> dict:
    from google.genai import types
    pcfg=cfg["generation_models"][model_key]
    client=_client(pcfg)
    parts=[types.Part.from_bytes(data=p.read_bytes(),mime_type=image_mime_type(p)) for p in inputs]
    response=client.models.generate_content(
        model=pcfg["model"],
        contents=[*parts,prompt],
        config=types.GenerateContentConfig(
            response_modalities=["TEXT","IMAGE"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio) if aspect_ratio else None,
            # No tools are used; disabling function calling also stops the SDK printing an AFC warning to users.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    reasons=[]; notes=[]
    for candidate in response.candidates or []:
        if getattr(candidate,"finish_reason",None): reasons.append(str(getattr(candidate.finish_reason,"name",candidate.finish_reason)))
        for part in getattr(candidate.content,"parts",[]) or []:
            inline=getattr(part,"inline_data",None)
            if inline and getattr(inline,"data",None):
                _write_image(inline.data,output)
                return {"model":pcfg["model"],"image_output_tokens":_image_output_tokens(response)}
            if getattr(part,"text",None): notes.append(part.text.strip())
    detail=f" (finish reason: {', '.join(reasons)})" if reasons else ""
    said=f" The model said: {' '.join(notes)[:300]}" if notes else ""
    raise RuntimeError(f"Image model returned no image{detail}. Nothing was saved; try rewording the prompt or using different input images.{said}")

# Terminal statuses where submitting a new job may succeed; other non-completed statuses are final.
_RETRYABLE_END={"failed","incomplete"}
_POLL_SECONDS=4
_DOWNLOAD_ATTEMPTS=3

def _http_status(e: Exception):
    return getattr(e,"status_code",None) or getattr(e,"code",None)

def _submit_error(e: Exception) -> VideoJobError:
    code=_http_status(e)
    # 4xx means the request itself was refused (bad input, key, permissions); resubmitting will not help.
    retryable=not (isinstance(code,int) and 400<=code<500 and code not in (408,429))
    return VideoJobError(f"Video request was refused: {type(e).__name__}: {e}",retryable=retryable)

def submit_video(prompt: str, reference: Path, cfg: dict, duration: int) -> str:
    pcfg=cfg["generation_models"]["video"]
    client=_client(pcfg)
    # The reference is sent inline: the API cannot report progress on background jobs that use uploaded files.
    input_parts=[
        {"type":"image","data":base64.b64encode(reference.read_bytes()).decode(),"mime_type":image_mime_type(reference)},
        {"type":"text","text":prompt},
    ]
    response_format={
        "type":"video","delivery":"uri",
        "aspect_ratio":cfg["video"]["aspect_ratio"],
        "resolution":str(cfg["video"]["resolution"]).lower(),
        "duration":f"{int(duration)}s",
    }
    try:
        interaction=client.interactions.create(model=pcfg["model"],input=input_parts,response_format=response_format,background=True)
    except Exception as e:
        raise _submit_error(e) from e
    if not getattr(interaction,"id",None): raise VideoJobError("Video provider accepted the request but returned no job id.",retryable=True)
    return interaction.id

def await_video(interaction_id: str, cfg: dict, output: Path, sleep=time.sleep, clock=time.monotonic) -> dict:
    """Poll a submitted job until it finishes, then download it. Never submits a new paid job."""
    client=_client(cfg["generation_models"]["video"])
    deadline=clock()+float(cfg["video"].get("timeout",600))
    interaction=None; last_error=None
    while True:
        try:
            interaction=client.interactions.get(interaction_id,include_input=False)
            status=str(interaction.status)
            if status not in ("queued","in_progress"): break
        except Exception as e:
            code=_http_status(e)
            if code==404: raise VideoJobError(f"Video job {interaction_id} no longer exists at the provider.",interaction_id,retryable=True) from e
            last_error=e  # transient polling failure; keep polling until the deadline
        if clock()>=deadline:
            detail=f" Last error: {last_error}" if last_error else ""
            raise VideoJobError(f"Video job {interaction_id} did not finish within {cfg['video'].get('timeout',600)}s. It may still complete; rerun the same command to collect it without paying again.{detail}",
                                interaction_id,resumable=True)
        sleep(_POLL_SECONDS)
    if status!="completed":
        errs="; ".join(str(getattr(x,"message",x)) for x in (getattr(interaction,"errors",None) or []))
        msg=f"Video job {interaction_id} ended with status '{status}'."+(f" {errs}" if errs else "")
        if status=="budget_exceeded": msg+=" Your Google account's spending limit was reached."
        raise VideoJobError(msg,interaction_id,retryable=status in _RETRYABLE_END)
    out=getattr(interaction,"output_video",None)
    if not out or not getattr(out,"uri",None):
        raise VideoJobError(f"Video job {interaction_id} completed without a video.",interaction_id,retryable=True)
    try:
        save_video(fetch_with_retry(lambda: client.files.download(file=out.uri),_DOWNLOAD_ATTEMPTS,_POLL_SECONDS,sleep),output)
    except Exception as e:
        raise VideoJobError(f"Video job {interaction_id} finished but could not be downloaded: {e}. Rerun the same command to download it without paying again.",
                            interaction_id,resumable=True) from e
    return {"interaction_id":interaction_id,"video_output_tokens":_video_output_tokens(interaction)}

def job_state(cfg: dict, interaction_id: str) -> str:
    """The job's status at Google (free): queued, in_progress, completed, failed, ..."""
    client=_client(cfg["generation_models"]["video"])
    return str(client.interactions.get(interaction_id,include_input=False).status)

def generate_video(prompt: str, reference: Path, cfg: dict, duration: int, output: Path, on_submitted=None) -> dict:
    iid=submit_video(prompt,reference,cfg,duration)
    if on_submitted: on_submitted(iid)
    return await_video(iid,cfg,output)

def _video_output_tokens(interaction):
    usage=getattr(interaction,"usage",None)
    for m in getattr(usage,"output_tokens_by_modality",None) or []:
        if str(getattr(m,"modality","")).lower().endswith("video"): return getattr(m,"tokens",None)
    return None
