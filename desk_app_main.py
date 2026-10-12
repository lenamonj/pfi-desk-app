"""The desk brief as a public app: the Course 8 brief as of 2026-10-02, from its snapshot, with no key.

Built in the Course 9 capstone from deploykit. GET /health, /brief, and /checks; POST /ask. Every response carries
the date its figures are from in the header X-Desk-As-Of. Every request is logged as one JSON line, with no body,
query, header value, or address. One process answers at most DAILY_CAP requests in a UTC day.
"""
import json
import os
from pathlib import Path

import deploykit

# the snapshot sits beside this file; Vercel bundles every file of the project the code can reach
SNAPSHOT_PATH = Path(__file__).parent / "desk_snapshot.json"
# the requests one process answers in a UTC day; the next get HTTP 429. A floor per process, not a guarantee: a
# serverless platform runs as many processes as the traffic needs, each with its own count
DAILY_CAP = 1000


def to_stdout(line: str) -> None:
    """A log line to standard output at once, where a platform's runtime logs read it."""
    print(line, flush=True)


def make_app(snapshot_path=SNAPSHOT_PATH, sink=to_stdout, clock=None, wall=None, daily_cap=DAILY_CAP, environ=None):
    """The desk service, with its as-of header, its daily cap, and its request log.

    Inputs: snapshot_path, the snapshot's JSON file; sink, a function given each log line (to_stdout on a
    platform, whose runtime logs keep what a function prints; a file append on your machine); clock and wall, the request
    log's clocks, wall also the cap's (deploykit.fake_clock in a notebook or a test, the real clocks by default);
    daily_cap, the requests answered in one UTC day; environ, the settings the mode is read from (os.environ by
    default).
    Output: a FastAPI app: deploykit.desk_app, then the cap, then the header X-Desk-As-Of on every response (a 404,
    a 422, and a 429 included), then the request log, outermost, so it logs every request the app answers.
    """
    snapshot = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    app = deploykit.desk_app(snapshot, deploykit.live_settings(os.environ if environ is None else environ))
    # a middleware added later runs earlier: the cap first (innermost), the log last (outermost)
    deploykit.daily_cap(app, daily_cap, wall=wall)

    @app.middleware("http")
    async def as_of_header(request, call_next):
        response = await call_next(request)
        response.headers["X-Desk-As-Of"] = snapshot["as_of"]
        return response

    return deploykit.log_middleware(app, sink, clock=clock, wall=wall)


# what the platform runs: each log line goes to standard output, which the platform keeps as runtime logs
app = make_app()
