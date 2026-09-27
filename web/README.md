# UBC Hub — web/

Next.js frontend. Two modes, chosen by whether `NEXT_PUBLIC_HUB_API` is set:

- **Sample mode** (default, no env var set): fixed fake data, no backend needed. This is what's hosted on Vercel.
- **Local mode**: talks to Jacky's `hub/api.py` running on the same laptop, for real Canvas/PrairieLearn data. Canvas/PrairieLearn logins open a browser window on your machine, so this only works run locally, never hosted.

## Run it locally (real data)

From the repo root:

```bash
uv run python -m hub.api          # starts the local API on http://localhost:8000
```

Then, in `web/`:

```bash
npm install                        # first time only
NEXT_PUBLIC_HUB_API=http://localhost:8000 npm run dev
```

Open http://localhost:3000, click **Connect Canvas** / **Connect PrairieLearn**, and sign in in the window that opens.

## Run it in Sample mode

```bash
npm install                        # first time only
npm run dev
```
