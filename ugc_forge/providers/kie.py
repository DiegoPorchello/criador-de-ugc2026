from __future__ import annotations
from pathlib import Path
import base64, json, time, urllib.error, urllib.parse, urllib.request
from .base import VideoJobError, image_mime_type, _write_image, resolve_key, fetch_with_retry, save_video

# kie.ai resells Google's models through one job API: upload inputs, create a task, poll it, download the
# result. API reference: https://docs.kie.ai (checked 2026-09-28).
BASE_URL="https://api.kie.ai"
# File uploads live on a separate host (per kie.ai's upload quickstart; the endpoint's own OpenAPI block
# says api.kie.ai, which returns 404 - confirmed live 2026-09-28).
UPLOAD_BASE_URL="https://kieai.redpandaai.co"
VIDEO_MODEL="google/gemini-omni-flash-1-1"   # Gemini Omni 1.1 Flash, the model Forge uses on Google
IMAGE_MODEL="nano-banana-pro"                 # Google's gemini-3-pro-image
SUPPORTED_VIDEO_DURATIONS={4,6,8,10}
SUPPORTED_VIDEO_RESOLUTIONS={"360p","720p","1080p","4k"}
SUPPORTED_VIDEO_ASPECTS={"16:9","9:16"}
_POLL_SECONDS=4
_DOWNLOAD_ATTEMPTS=3
# Refused requests that will not succeed if sent again.
_FINAL_CODES={400,401,402,403,404,413,422}

class KieError(Exception):
    def __init__(self, code, message):
        super().__init__(message); self.code=code

def resolve_api_key(kcfg: dict) -> str:
    return resolve_key(kcfg,"kie.ai")

def _explain(code, message: str) -> str:
    if code==401: return "kie.ai rejected the API key. Run `ugc-forge setup` to enter it again."
    if code==402: return "Your kie.ai credits have run out. Top up at https://kie.ai, then rerun the same command."
    if code==429: return "kie.ai is rate-limiting requests; try again shortly."
    return f"kie.ai error{f' {code}' if code else ''}: {message}"

def _request(cfg: dict, method: str, path: str, body: dict|None=None, timeout: float=120, base: str=BASE_URL):
    key=resolve_api_key(cfg["kie"])
    req=urllib.request.Request(base+path,method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r: payload=json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: msg=json.loads(e.read() or b"{}").get("msg") or e.reason
        except ValueError: msg=e.reason
        raise KieError(e.code,_explain(e.code,str(msg))) from e
    except (urllib.error.URLError,TimeoutError,OSError) as e:
        raise KieError(None,f"Could not reach kie.ai: {getattr(e,'reason',e)}") from e
    code=payload.get("code")
    if code not in (None,200):
        raise KieError(code,_explain(code,str(payload.get("msg"))))
    return payload.get("data")

def credits(cfg: dict) -> int:
    """Remaining credit balance. Free; used to check the key."""
    return _request(cfg,"GET","/api/v1/chat/credit")

def upload(cfg: dict, path: Path) -> str:
    # kie.ai needs image URLs; its own upload API returns a temporary one, so nothing is hosted publicly by us.
    data=f"data:{image_mime_type(path)};base64,{base64.b64encode(path.read_bytes()).decode()}"
    out=_request(cfg,"POST","/api/file-base64-upload",{"base64Data":data,"uploadPath":"ugc-forge","fileName":path.name},base=UPLOAD_BASE_URL) or {}
    url=out.get("downloadUrl") or out.get("fileUrl")
    if not url: raise KieError(None,"kie.ai accepted the upload but returned no file URL.")
    return url

def _create(cfg: dict, model: str, inputs: dict) -> str:
    out=_request(cfg,"POST","/api/v1/jobs/createTask",{"model":model,"input":inputs})
    tid=(out or {}).get("taskId")
    if not tid: raise KieError(None,"kie.ai accepted the request but returned no task id.")
    return tid

def _download(cfg: dict, url: str) -> bytes:
    def get(u):
        with urllib.request.urlopen(urllib.request.Request(u),timeout=300) as r: return r.read()
    try: return get(url)
    except urllib.error.HTTPError as e:
        if e.code not in (401,403,404): raise
        # Some generated files need a short-lived signed link first.
        return get(_request(cfg,"POST","/api/v1/common/download-url",{"url":url}))

def timeout(cfg: dict) -> float:
    # kie.ai jobs can sit in its queue far longer than Google's, so it has its own, longer wait.
    return float((cfg.get("kie") or {}).get("timeout") or cfg["video"].get("timeout",600))

_STATE_WORDS={"waiting":"still waiting in kie.ai's queue","queuing":"still queued at kie.ai","generating":"still generating at kie.ai"}

def _poll(cfg: dict, task_id: str, deadline: float, sleep, clock) -> dict:
    last=None; state=None
    while True:
        try:
            info=_request(cfg,"GET","/api/v1/jobs/recordInfo?"+urllib.parse.urlencode({"taskId":task_id}))
            state=info.get("state")
            if state in ("success","fail"): return info
        except KieError as e:
            if e.code in _FINAL_CODES and e.code!=404: raise
            if e.code==404: raise VideoJobError(f"kie.ai task {task_id} no longer exists.",task_id,retryable=True) from e
            last=e  # transient; keep polling until the deadline
        if clock()>=deadline:
            detail=f" Last error: {last}" if last else ""
            where=_STATE_WORDS.get(state,"not finished")
            raise VideoJobError(f"kie.ai task {task_id} is {where} after {int(timeout(cfg)//60)} minutes. It is already paid for; "
                                f"rerun the same command later to collect it without paying again.{detail}",task_id,resumable=True)
        sleep(_POLL_SECONDS)

def job_state(cfg: dict, task_id: str) -> str:
    """The task's state at kie.ai (free): waiting, queuing, generating, success or fail."""
    return str(_request(cfg,"GET","/api/v1/jobs/recordInfo?"+urllib.parse.urlencode({"taskId":task_id})).get("state"))

def _result_url(info: dict) -> str|None:
    raw=info.get("resultJson")
    try: urls=(json.loads(raw) if isinstance(raw,str) else (raw or {})).get("resultUrls") or []
    except ValueError: urls=[]
    return urls[0] if urls else None

def validate_video_config(cfg: dict):
    res=str(cfg["video"]["resolution"]).lower(); ar=str(cfg["video"]["aspect_ratio"])
    if res not in SUPPORTED_VIDEO_RESOLUTIONS: raise ValueError(f"Unsupported resolution: {res}")
    if ar not in SUPPORTED_VIDEO_ASPECTS: raise ValueError(f"Unsupported aspect ratio: {ar}")
    durations={int(x) for x in cfg["timing"].get("supported_durations",sorted(SUPPORTED_VIDEO_DURATIONS))}
    if not durations & SUPPORTED_VIDEO_DURATIONS:
        raise ValueError(f"kie.ai supports durations {sorted(SUPPORTED_VIDEO_DURATIONS)}.")

def submit_video(prompt: str, reference: Path, cfg: dict, duration: int) -> str:
    try:
        url=upload(cfg,reference)
        return _create(cfg,VIDEO_MODEL,{"prompt":prompt,"image_urls":[url],"duration":str(int(duration)),
                                        "aspect_ratio":cfg["video"]["aspect_ratio"],"resolution":str(cfg["video"]["resolution"]).lower()})
    except KieError as e:
        raise VideoJobError(f"Video request was refused: {e}",retryable=e.code not in _FINAL_CODES) from e

def await_video(task_id: str, cfg: dict, output: Path, sleep=time.sleep, clock=time.monotonic) -> dict:
    """Poll a submitted task until it finishes, then download it. Never submits a new paid task."""
    try: info=_poll(cfg,task_id,clock()+timeout(cfg),sleep,clock)
    except KieError as e: raise VideoJobError(str(e),task_id,retryable=False) from e
    if info.get("state")=="fail":
        # Worth another attempt. kie.ai refunds failed tasks: a failed task reported creditsConsumed 0 (2026-09-29).
        raise VideoJobError(f"kie.ai task {task_id} failed ({info.get('failMsg') or info.get('failCode') or 'no reason given'}); "
                            "kie.ai doesn't charge failed tasks.",task_id,retryable=True)
    url=_result_url(info)
    if not url: raise VideoJobError(f"kie.ai task {task_id} completed without a video.",task_id,retryable=True)
    try:
        save_video(fetch_with_retry(lambda: _download(cfg,url),_DOWNLOAD_ATTEMPTS,_POLL_SECONDS,sleep),output)
    except Exception as e:
        raise VideoJobError(f"kie.ai task {task_id} finished but could not be downloaded: {e}. Rerun the same command to download it without paying again.",
                            task_id,resumable=True) from e
    return {"interaction_id":task_id,"provider":"kie","credits":info.get("creditsConsumed")}

def generate_image(inputs: list[Path], prompt: str, cfg: dict, output: Path, aspect_ratio: str|None=None, model_key: str="image",
                   sleep=time.sleep, clock=time.monotonic) -> dict:
    try:
        urls=[upload(cfg,p) for p in inputs]
        tid=_create(cfg,IMAGE_MODEL,{"prompt":prompt,"image_input":urls,"aspect_ratio":aspect_ratio or "auto",
                                     "resolution":"1K","output_format":"png"})
        info=_poll(cfg,tid,clock()+timeout(cfg),sleep,clock)
    except (KieError,VideoJobError) as e:
        raise RuntimeError(f"Image request failed: {e}") from e
    url=_result_url(info) if info.get("state")=="success" else None
    if not url:
        reason=info.get("failMsg") or info.get("failCode") or "no image returned"
        raise RuntimeError(f"Image model returned no image ({reason}). Nothing was saved; try rewording the prompt or using different input images.")
    try:
        # The image is already paid for, so a transient download failure is retried rather than lost.
        _write_image(fetch_with_retry(lambda: _download(cfg,url),_DOWNLOAD_ATTEMPTS,_POLL_SECONDS,sleep),output)
    except Exception as e:
        raise RuntimeError(f"kie.ai made the image (task {tid}), and charged for it, but it couldn't be downloaded after "
                           f"{_DOWNLOAD_ATTEMPTS} tries: {e}. Running the command again makes and charges for a new image.") from e
    return {"model":IMAGE_MODEL,"provider":"kie","credits":info.get("creditsConsumed")}
