"""TriageIQ API — score a CFPB complaint: will the company pay? -> senior analyst or template response.

Run on the Mac (from the repo root):  sh api/run_local.sh     then open http://localhost:8000/docs
(it reads the database password from .env; the API itself reads the standard PG* environment variables)

Design (Learning/Phase3/directions.md, step 3.4):
  - The caller sends NAMES + TEXT, never features. Features come from SQL (serving.model_input), the same
    formulas training used, skew-tested — one source of truth (ground rule 4). Trade-off: every request needs
    a database round trip, and the API is down when the database is.
  - The model, tokenizer and database pool are loaded ONCE at startup (lifespan), not per request.
  - Endpoints are plain `def`, not `async def`: scoring keeps the CPU busy (no waiting to hand over), so
    FastAPI runs them on its thread pool and one slow request doesn't freeze the others.
  - Explanations ("why this score?") take ~2–100 s on the server, so they don't answer in the request: POST
    /explain (or POST /complaint/{id}/explain) returns a TICKET at once, GET /explain/jobs/{id} shows its place in
    line and, when done, the explanation. One runs at a time (api/jobs.py). They need the xai_* model files
    (GitHub Release model-v3); without them the endpoints are hidden from /docs and answer 503.
"""
import hashlib, json, os, time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse

from api import db
from api.jobs import Line, LineFull
from api.schemas import ComplaintIn, ComplaintOut, ExplainTicket, Explanation, Prediction
from api.scorer import Scorer

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "training/outputs/serving_v3"))
THREADS = int(os.environ.get("ORT_THREADS", "2"))
XAI_BATCH = int(os.environ.get("XAI_BATCH", "8"))         # texts per DistilBERT pass while explaining (server: 4)
XAI_MAX_WAITING = int(os.environ.get("XAI_MAX_WAITING", "20"))
XAI_FILES = ("xai_encoder.onnx", "xai_head.onnx", "xai_background.npz")
XAI_READY = all((MODEL_DIR / f).is_file() for f in XAI_FILES) and (Path(__file__).parent / "xai.py").is_file()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.scorer = Scorer(MODEL_DIR, THREADS)          # ~1 s: the 266 MB model is read once
    db.pool.open(wait=True, timeout=30)
    with db.pool.connection() as conn:
        app.state.as_of = db.snapshot_day(conn)
    if XAI_READY:                                          # shares the scorer's model: no second copy in memory
        from api.xai import Explainer
        app.state.explainer = Explainer(MODEL_DIR, app.state.scorer, THREADS, batch=XAI_BATCH)
        app.state.line = Line(lambda job: _explanation(*job), max_waiting=XAI_MAX_WAITING)
    yield
    db.pool.close()


app = FastAPI(
    title="TriageIQ",
    version="v3",
    lifespan=lifespan,
    description=(
        "Predicts whether a CFPB consumer complaint will end with the company paying money, so a compliance desk "
        "can send the riskiest complaints to a senior analyst.\n\n"
        "**Try it:** `GET /complaint/random` shows a real 2024 complaint, the model's call and what actually "
        "happened. `POST /predict` scores a complaint you write (an example is filled in).\n\n"
        "A DistilBERT reads the text; 19 track-record numbers (computed in SQL, as of the end of 2024) describe "
        "the company and the kind of problem. Tested on 150,000 complaints from 2024. Details: `GET /model-info`."),
)


def _route(senior: bool) -> str:
    return "senior analyst" if senior else "template response"


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.post("/predict", response_model=Prediction, tags=["score"])
def predict(c: ComplaintIn):
    """Score a NEW complaint: names + text in, chance of a payout and a route out."""
    t0 = time.perf_counter()
    with db.pool.connection() as conn:
        try:
            ids, notes = db.resolve(conn, c.company, c.product, c.sub_product, c.issue, c.state)
        except db.NotFound as e:
            raise HTTPException(status_code=422, detail=str(e))
        inputs = db.model_input(conn, ids, c.older_american, c.servicemember)
        text = db.clean(conn, c.narrative)
    s = app.state.scorer.score(text, inputs)
    return Prediction(
        payout_probability=round(s["probability"], 5), route=_route(s["senior"]),
        senior_threshold=round(app.state.scorer.cal["senior_threshold_p"], 5),
        model_version=app.state.scorer.card["model_version"], features_as_of=app.state.as_of,
        inputs={k: round(float(v), 6) for k, v in inputs.items()},
        text_word_pieces=s["word_pieces"], text_cut_at_512=s["cut_at_512"], notes=notes,
        latency_ms=round((time.perf_counter() - t0) * 1000, 1))


@app.get("/complaint/random", response_model=ComplaintOut, tags=["demo"])
def random_complaint(paid: bool | None = Query(default=None, description="true = one the company paid; "
                                                "false = one it didn't; empty = any")):
    """A random real complaint from 2024 (the test set the model never saw): its score vs what happened."""
    with db.pool.connection() as conn:
        cid = db.random_test_complaint(conn, paid)
    return complaint(cid)


@app.get("/complaint/{complaint_id}", response_model=ComplaintOut, tags=["demo"])
def complaint(complaint_id: int):
    """One real 2024 complaint by its CFPB id: the model's call (with the track record as of the day it arrived)
    next to what the company actually did."""
    t0 = time.perf_counter()
    with db.pool.connection() as conn:
        r = db.test_complaint(conn, complaint_id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"complaint {complaint_id} is not in the 2024 demo set "
                                                     "(try GET /complaint/random)")
    inputs = {k: r[k] for k in db.INPUTS}
    s = app.state.scorer.score(r["text"], inputs)
    return ComplaintOut(
        payout_probability=round(s["probability"], 5), route=_route(s["senior"]),
        senior_threshold=round(app.state.scorer.cal["senior_threshold_p"], 5),
        model_version=app.state.scorer.card["model_version"], features_as_of=r["date_received"],
        inputs={k: round(float(v), 6) for k, v in inputs.items()},
        text_word_pieces=s["word_pieces"], text_cut_at_512=s["cut_at_512"], notes=[],
        latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        complaint_id=r["complaint_id"], date_received=r["date_received"], company=r["company_name"],
        product=r["product_name"], sub_product=r["sub_product_name"], issue=r["issue_name"], state=r["state_code"],
        narrative=r["text"], what_actually_happened=r["company_response"], actually_paid=bool(r["paid"]))


# ---------------------------------------------------------------- explanations: a ticket now, the answer later
def _explanation(text: str, inputs: dict) -> Explanation:
    """Runs on the line's worker thread, one at a time."""
    t0 = time.perf_counter()
    r = app.state.explainer.explain(text, inputs)
    bad = {k: v for k, v in r["checks"].items() if v > 1e-4}
    if bad:                                                # never show an explanation that doesn't add up
        raise RuntimeError(f"explanation failed its own checks: {bad}")
    return Explanation(
        payout_probability=round(r["probability"], 5), route=_route(r["senior"]),
        typical_probability=r["typical_probability"], factors=r["factors"], sentences=r["sentences"],
        sentence_method=r["sentence_method"], words_not_read=r["words_not_read"], text=text,
        checks=r["checks"], latency_ms=round((time.perf_counter() - t0) * 1000, 1))


def _ticket(text: str, inputs: dict) -> ExplainTicket:
    if not XAI_READY:
        raise HTTPException(status_code=503, detail="Explanations aren't available here (the xai_* model files are missing).")
    key = hashlib.sha256(json.dumps({"text": text, "inputs": {k: float(v) for k, v in inputs.items()}},
                                    sort_keys=True).encode()).hexdigest()   # same complaint -> same job / cached answer
    try:
        return ExplainTicket(**app.state.line.submit(key, (text, inputs)))
    except LineFull as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/explain/status", include_in_schema=False)
def explain_status():
    """For the website: offer "Why this score?" only where explanations work, and say how busy the line is."""
    return {"available": XAI_READY, **(app.state.line.status() if XAI_READY else {})}


@app.post("/explain", response_model=ExplainTicket, tags=["explain"], include_in_schema=XAI_READY)
def explain(c: ComplaintIn):
    """WHY did the model give this score? Same input as /predict. Returns a TICKET at once — then poll
    `GET /explain/jobs/{job_id}`: "queued" (with your place in line) → "running" → "done" (+ the explanation).
    The explanation: shares of the score for the words and 10 groups of track-record inputs (exact Shapley values),
    and for each sentence (Shapley values over sentences, by deleting and re-reading). On the server it takes
    ~2 s for a short complaint, up to ~100 s for a long one; one runs at a time."""
    with db.pool.connection() as conn:
        try:
            ids, _ = db.resolve(conn, c.company, c.product, c.sub_product, c.issue, c.state)
        except db.NotFound as e:
            raise HTTPException(status_code=422, detail=str(e))
        inputs = db.model_input(conn, ids, c.older_american, c.servicemember)
        text = db.clean(conn, c.narrative)
    return _ticket(text, inputs)


@app.post("/complaint/{complaint_id}/explain", response_model=ExplainTicket, tags=["explain"],
          include_in_schema=XAI_READY)
def explain_complaint(complaint_id: int):
    """WHY did the model give this real 2024 complaint its score? Returns a ticket (see POST /explain)."""
    with db.pool.connection() as conn:
        r = db.test_complaint(conn, complaint_id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"complaint {complaint_id} is not in the 2024 demo set")
    return _ticket(r["text"], {k: r[k] for k in db.INPUTS})


@app.get("/explain/jobs/{job_id}", response_model=ExplainTicket, tags=["explain"], include_in_schema=XAI_READY)
def explain_job(job_id: str):
    """Your ticket: place in line, or the finished explanation. Tickets are kept 30 minutes after they finish."""
    t = app.state.line.view(job_id) if XAI_READY else None
    if t is None:
        raise HTTPException(status_code=404, detail="no such explanation ticket (they expire 30 minutes after finishing)")
    return ExplainTicket(**t)


@app.get("/options/{what}", tags=["options"])
def options(what: str, search: str | None = Query(default=None, min_length=2, max_length=100,
                                                   description="companies only: part of the name, e.g. 'wells'")):
    """Valid names for /predict: `products` (with sub-products), `issues`, `states`, `companies?search=...`."""
    if what not in ("products", "issues", "states", "companies"):
        raise HTTPException(status_code=404, detail="use products, issues, states or companies")
    if what == "companies" and not search:
        raise HTTPException(status_code=422, detail="add ?search= with part of the company name")
    with db.pool.connection() as conn:
        return db.options(conn, what, search)


@app.get("/health", tags=["service"])
def health():
    """Is the service up, the model loaded, and the database reachable?"""
    try:
        with db.pool.connection() as conn:
            day = db.snapshot_day(conn)
        return {"status": "ok", "model_loaded": True, "database": "ok", "features_as_of": day}
    except Exception as e:                                  # report, don't crash: health must always answer
        raise HTTPException(status_code=503, detail=f"database unavailable: {type(e).__name__}")


@app.get("/model-info", tags=["service"])
def model_info():
    """What the model is, how it was tested, how probabilities are calibrated, and its limits."""
    return app.state.scorer.card | {"features_as_of_live": str(app.state.as_of)}
