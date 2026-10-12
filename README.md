# PFI desk brief

**The Course 8 credit desk's morning brief at a public address: the date its figures are from, the checks it passed, and a refusal for any request for a view.**

> This course is educational content created in a personal capacity. Nothing here is investment advice or a recommendation to buy or sell any security. All portfolio data is synthetic.

Every figure is as of 2026-10-02 in the course's files, and the app does not update them. A request in a later year gets the same figures and the same date: every response carries the header `X-Desk-As-Of: 2026-10-02`.

## What it serves

| Request | Returns |
| --- | --- |
| `GET /health` | `status`, `version`, `as_of`, and `mode` (always `replay` here) |
| `GET /brief` | the brief in three sections (macro, documents, portfolio), each with its text, figures, and sources |
| `GET /checks` | the check table the brief passed and failed, as Course 8's capstone wrote it |
| `POST /ask` with `{"question": "..."}` | the saved answer to a question Course 8's capstone recorded; HTTP 404 for any other question; the refusal line for a request for a view |

## What it does not do

* It gives no view on any security, issuer, or rate, and refuses a request for one before anything is looked up.
* It answers only the questions Course 8's capstone recorded. Any other question gets HTTP 404 and a reason, never a guess.
* It holds no key and sends no request to a model: it serves a snapshot of saved runs, `desk_snapshot.json`, with the SHA-256 of every saved exchange its figures came from.
* Its holdings are synthetic. A real company appears only as the author of a document, never beside a holding.

## Run it on your machine

```powershell
python -m pip install -r requirements-test.txt
python -m pytest -q test_desk_app.py
python -m uvicorn app:app --port 8000
```

## What it is for

A course exercise: personal, educational, and non-commercial, which is the only use Vercel's free Hobby plan allows. Logs hold one line per request (time, path, status, latency, size, whether it was refused), never the question asked.

## What it costs

Nothing, inside the free tiers read on 2026-10-12: Vercel Hobby includes 1,000,000 function invocations, 4 CPU hours, and 100 GB of fast data transfer a month (vercel.com/docs/plans/hobby), and keeps runtime logs for 1 hour (vercel.com/docs/logs/runtime); GitHub Actions is free on a public repository. One process answers at most 1,000 requests in a UTC day; a serverless platform runs many processes, so the cap is a floor, not a guarantee. The app sends no request to a model, so it has no model bill.

## Also on

A Hugging Face Space, optional: the same snapshot as a Gradio app on ZeroGPU. A free account may host up to 2 ZeroGPU Spaces once it is older than 30 days with a verified email (huggingface.co/docs/hub/spaces-zerogpu, read 2026-10-12).
