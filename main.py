import os
import json
import asyncio
import tempfile
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import google.generativeai as genai

# ── Config ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "w7oVeNTUkRl1Jq3zw0bx")
HEYGEN_API_KEY = os.getenv("HEYGEN_API_KEY", "")
HEYGEN_AVATAR_ID = os.getenv("HEYGEN_AVATAR_ID", "eb195f829ab4465f97b70fae273e696a")
_HEYGEN_GENERATE_URL = "https://api.heygen.com/v2/video/generate"
_HEYGEN_STATUS_URL = "https://api.heygen.com/v1/video_status.get"
_HEYGEN_UPLOAD_URL = "https://upload.heygen.com/v1/asset"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

app = FastAPI(title="Aura — AI Presence Layer")
app.mount("/static", StaticFiles(directory="static"), name="static")


def _heygen_api_headers() -> dict[str, str]:
    return {"X-Api-Key": HEYGEN_API_KEY.strip(), "Content-Type": "application/json"}


def _heygen_upload_headers() -> dict[str, str]:
    return {"X-API-KEY": HEYGEN_API_KEY.strip(), "Content-Type": "audio/mpeg"}


async def _elevenlabs_tts_to_mp3_file(client: httpx.AsyncClient, text: str, out_path: str) -> None:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    body = {"text": text, "model_id": "eleven_multilingual_v2"}
    res = await client.post(url, headers=headers, json=body, timeout=120.0)
    if res.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"ElevenLabs TTS failed ({res.status_code}): {res.text[:800]}",
        )

    def _write() -> None:
        with open(out_path, "wb") as f:
            f.write(res.content)

    await asyncio.to_thread(_write)


async def _heygen_upload_mp3_asset_url(client: httpx.AsyncClient, mp3_path: str) -> str:
    """Upload MP3 to HeyGen; returned URL is valid for video_inputs.voice.audio_url."""

    def _read() -> bytes:
        with open(mp3_path, "rb") as f:
            return f.read()

    body = await asyncio.to_thread(_read)
    res = await client.post(
        _HEYGEN_UPLOAD_URL,
        headers=_heygen_upload_headers(),
        content=body,
        timeout=120.0,
    )
    if res.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"HeyGen audio upload failed ({res.status_code}): {res.text[:800]}",
        )
    payload = res.json()
    if payload.get("code") != 100:
        raise HTTPException(
            status_code=502,
            detail=f"HeyGen audio upload error: {payload}",
        )
    url = ((payload.get("data") or {}).get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=502, detail="HeyGen upload returned no url")
    return url


async def _heygen_audio_url_from_script(client: httpx.AsyncClient, text: str) -> str:
    """ElevenLabs TTS → temp MP3 → HeyGen asset upload → public audio URL for /v2/video/generate."""
    fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        await _elevenlabs_tts_to_mp3_file(client, text, tmp_path)
        return await _heygen_upload_mp3_asset_url(client, tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Request models ───────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    topic: str
    platform: str = "linkedin"


class VideoRequest(BaseModel):
    script: str


def _key_preview(key: str, n: int = 8) -> str:
    k = (key or "").strip()
    return k[:n] + "..." if k else "..."


# ── Routes ───────────────────────────────────────────────────────────────────
@app.get("/debug")
@app.get("/debug/config")
async def debug_config():
    """Masked provider keys. Disabled when AURA_DEBUG_CONFIG is 0, false, or no."""
    off = os.getenv("AURA_DEBUG_CONFIG", "1").strip().lower()
    if off in ("0", "false", "no"):
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "gemini_key": _key_preview(GEMINI_API_KEY),
        "heygen_key": _key_preview(HEYGEN_API_KEY),
        "heygen_avatar_id": HEYGEN_AVATAR_ID.strip(),
        "elevenlabs_key": _key_preview(ELEVENLABS_API_KEY),
        "elevenlabs_voice_id": ELEVENLABS_VOICE_ID.strip(),
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse("static/index.html")


@app.post("/generate")
async def generate_content(req: GenerateRequest):
    prompt = f"""You are Aura, an expert AI brand strategist and content creator.

The user wants to create content about: "{req.topic}"
Target platform: {req.platform}

Generate TWO pieces of content and return ONLY valid JSON (no markdown, no backticks):

{{
  "linkedin_post": "A compelling LinkedIn post (150-200 words). Professional but human tone. Include 3-5 relevant hashtags at the end. Use line breaks for readability.",
  "video_script": "A 30-45 second video script (spoken words only, no stage directions). Conversational, engaging, first-person. Should feel natural when spoken aloud.",
  "image_prompt": "A vivid, specific prompt for generating a thumbnail image that matches this content.",
  "hook": "A 10-word attention-grabbing hook for the video opening"
}}"""

    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        data = json.loads(raw)
        return {"success": True, "data": data}
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"JSON parse error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-video")
async def generate_video(req: VideoRequest):
    script_text = req.script.strip()
    if len(script_text) < 3:
        raise HTTPException(status_code=422, detail="Video script must be at least 3 characters.")
    if not HEYGEN_API_KEY.strip():
        raise HTTPException(status_code=422, detail="HEYGEN_API_KEY is required.")
    if not HEYGEN_AVATAR_ID.strip():
        raise HTTPException(status_code=422, detail="HEYGEN_AVATAR_ID is required.")

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            audio_url = await _heygen_audio_url_from_script(client, script_text)
            hg_body = {
                "video_inputs": [
                    {
                        "character": {
                            "type": "avatar",
                            "avatar_id": HEYGEN_AVATAR_ID.strip(),
                            "avatar_style": "normal",
                        },
                        "voice": {"type": "audio", "audio_url": audio_url},
                    }
                ],
                "dimension": {"width": 1280, "height": 720},
            }
            res = await client.post(
                _HEYGEN_GENERATE_URL,
                headers=_heygen_api_headers(),
                json=hg_body,
            )
            if res.status_code not in (200, 201):
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"HeyGen error: {res.text[:1200]}",
                )
            job = res.json()
            if job.get("error"):
                raise HTTPException(status_code=502, detail=f"HeyGen: {job.get('error')}")
            video_id = (job.get("data") or {}).get("video_id")
            if not video_id:
                raise HTTPException(status_code=502, detail=f"HeyGen returned no video_id: {job}")
            return {"success": True, "talk_id": f"heygen_{video_id}", "status": "processing"}
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Request error: {str(e)}")


@app.get("/video-status/{talk_id}")
async def video_status(talk_id: str):
    video_id = talk_id.removeprefix("heygen_") if talk_id.startswith("heygen_") else talk_id
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.get(
            _HEYGEN_STATUS_URL,
            headers={"X-Api-Key": HEYGEN_API_KEY.strip()},
            params={"video_id": video_id},
        )
        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail=res.text[:1200])
        body = res.json()
        code = body.get("code")
        if code is not None and code not in (100, "100"):
            raise HTTPException(status_code=502, detail=str(body)[:1200])
        data = body.get("data") or {}
        st = (data.get("status") or "").strip()
        url = (data.get("video_url") or "").strip()
        if st == "completed":
            return {"success": True, "status": "done", "video_url": url, "done": True}
        if st == "failed":
            err = data.get("error")
            if isinstance(err, dict):
                msg = (err.get("message") or err.get("detail") or str(err))[:800]
            else:
                msg = (str(err) if err else "HeyGen render failed")[:800]
            return {
                "success": True,
                "status": "failed",
                "video_url": "",
                "done": True,
                "error": msg,
            }
        return {"success": True, "status": st, "video_url": url, "done": False}

