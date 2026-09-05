# Glancy voice frontend

React + Vite UI for the Pipecat SmallWebRTC voice bot.

## Setup

```bash
cd frontend
npm install
cp .env.example .env
```

## Run

Start the bot first:

```bash
# from repo root
source .venv/bin/activate
python -m bot.main
```

Then:

```bash
npm run dev
```

Open http://localhost:5173 — Connect, allow the microphone, and talk.

`VITE_BOT_OFFER_URL` defaults to `/api/offer` (proxied to `http://localhost:7860`).
