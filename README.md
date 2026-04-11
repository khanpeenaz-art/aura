# Aura — AI Presence Layer

> Speak your ideas. Aura turns them into polished LinkedIn posts, video scripts, and AI avatar videos — published to social media automatically.

## Team Members
| Name | Role |
|---|---|
| Peenaz Khan | Builder & Product Lead |

## What it does
Aura is a **Creative Storyteller AI agent** built for the NYC Build With AI Hackathon.

1. **Input** — User types a topic or idea into the web app
2. **Generate** — Gemini 2.0 Flash generates a LinkedIn post + video script + hook simultaneously (interleaved multimodal output)
3. **Review** — User reads both outputs and edits if needed
4. **Approve** — User clicks "Generate Avatar Video" — only then does the video get created
5. **Publish** — AI avatar video published to LinkedIn and social media

## Tech Stack
- **LLM:** Google Gemini 2.0 Flash (Google GenAI SDK)
- **Backend:** FastAPI (Python)
- **Avatar Video:** HeyGen API (ElevenLabs TTS → HeyGen asset → avatar video)
- **Hosting:** Google Cloud Run
- **Frontend:** Vanilla HTML/CSS/JS

## Architecture
```
User Input (Web)
      ↓
FastAPI Backend
      ↓
Gemini 2.0 Flash ──→ LinkedIn Post + Video Script + Hook
      ↓ (user approves)
HeyGen API ──→ Avatar Video Generated
      ↓
Published to Social Media
```

## Run Locally
```bash
git clone <repo-url>
cd aura
pip install -r requirements.txt
uvicorn main:app --reload
# Open http://localhost:8000
```

## Deploy to Google Cloud Run
```bash
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/aura
gcloud run deploy aura \
  --image gcr.io/YOUR_PROJECT_ID/aura \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

## Environment Variables
```
GEMINI_API_KEY=your_gemini_key
HEYGEN_API_KEY=your_heygen_key
HEYGEN_AVATAR_ID=your_avatar_id
ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_ID=your_voice_id
# Optional: GEMINI_MODEL=gemini-2.5-flash
# Optional: AURA_DEBUG_CONFIG=0  → hide GET /debug and /debug/config (masked keys; on by default)
```

## Hackathon Category
**Creative Storyteller** — Multimodal content generation using Gemini's interleaved output capabilities, deployed on Google Cloud.
