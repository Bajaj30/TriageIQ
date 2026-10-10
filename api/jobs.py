"""A waiting line for slow work: one explanation at a time, everyone else takes a ticket and checks back.

WHY: on the server's 2 CPU cores an explanation takes ~2 s (short complaint) to ~100 s (long one) — the text is
re-read up to ~250 times (api/xai.py). Holding a web request open that long breaks: our NGINX gives up after 30 s,
and two explanations at once would only slow each other AND every visitor's ordinary score. So:
  submit()  -> a ticket at once: {job_id, status "queued", position = explanations ahead of you, wait estimate}
  view()    -> the same ticket later: "queued" → "running" → "done" (+ the explanation) or "failed" (+ why)
  one worker thread takes tickets in arrival order (first come, first served) and runs them one by one.
Like a deli counter: take a number, watch the board.

Three courtesies: the SAME complaint asked twice while waiting shares one job (a room full of people clicking the
same example); a finished explanation is kept (cache) and returned instantly next time; and at most `max_waiting`
tickets wait — past that, submit() says the line is full instead of promising a wait of hours.
Tickets are forgotten `keep_s` seconds after they finish. Everything lives in memory: a restart empties the line.
"""
import collections, threading, time, uuid


class LineFull(Exception):
    pass


class Line:
    def __init__(self, work, max_waiting: int = 20, keep_s: float = 1800, cache_size: int = 500,
                 typical_s: float = 45.0):
        self.work = work                                   # payload -> result; runs on the worker thread
        self.max_waiting, self.keep_s, self.cache_size = max_waiting, keep_s, cache_size
        self.jobs: dict[str, dict] = {}
        self.waiting: collections.deque[str] = collections.deque()
        self.pending: dict[str, str] = {}                  # content key -> id of its queued/running job
        self.cache: collections.OrderedDict = collections.OrderedDict()   # content key -> result (newest last)
        self.durations = collections.deque([typical_s], maxlen=10)        # recent run times, for the estimate
        self.running: str | None = None
        self.cv = threading.Condition()
        threading.Thread(target=self._loop, daemon=True, name="explain-line").start()

    # -------------------------------------------------- the counter
    def submit(self, key: str, payload) -> dict:
        with self.cv:
            self._forget_old()
            if key in self.cache:                          # explained before: answer at once
                self.cache.move_to_end(key)
                jid = self._new(key, status="done", result=self.cache[key], finished=time.time())
                return self._view(jid)
            if key in self.pending:                        # the same complaint is already in line: share it
                return self._view(self.pending[key])
            if len(self.waiting) >= self.max_waiting:
                raise LineFull(f"{len(self.waiting)} explanations are already waiting — try again in a few minutes")
            jid = self._new(key, status="queued", payload=payload)
            self.pending[key] = jid
            self.waiting.append(jid)
            self.cv.notify()
            return self._view(jid)

    def view(self, jid: str) -> dict | None:
        with self.cv:
            return self._view(jid) if jid in self.jobs else None

    def status(self) -> dict:
        with self.cv:
            return {"waiting": len(self.waiting), "running": self.running is not None,
                    "typical_seconds": round(self._typical(), 1)}

    # -------------------------------------------------- inside
    def _new(self, key, **fields) -> str:
        jid = uuid.uuid4().hex[:16]
        self.jobs[jid] = {"key": key, "created": time.time(), **fields}
        return jid

    def _typical(self) -> float:
        return sum(self.durations) / len(self.durations)

    def _view(self, jid: str) -> dict:
        job = self.jobs[jid]
        out = {"job_id": jid, "status": job["status"], "position": None, "wait_estimate_s": None,
               "running_for_s": None, "result": None, "error": None}
        if job["status"] == "queued":
            ahead = self.waiting.index(jid) + (1 if self.running else 0)      # explanations before yours
            out["position"] = ahead
            out["wait_estimate_s"] = round((ahead + 1) * self._typical())    # rough: until yours is done
        elif job["status"] == "running":
            out["position"] = 0
            out["running_for_s"] = round(time.time() - job["started"], 1)
        elif job["status"] == "done":
            out["result"] = job["result"]
        else:
            out["error"] = job["error"]
        return out

    def _loop(self):
        while True:
            with self.cv:
                while not self.waiting:
                    self.cv.wait()
                jid = self.waiting.popleft()
                job = self.jobs[jid]
                job["status"], job["started"], self.running = "running", time.time(), jid
            try:
                result, error = self.work(job["payload"]), None
            except Exception as e:                         # a failed explanation must never stop the line
                result, error = None, getattr(e, "detail", None) or f"{type(e).__name__}: {e}"
            with self.cv:
                self.durations.append(time.time() - job["started"])
                self.running = None
                self.pending.pop(job["key"], None)
                job.pop("payload", None)
                job["finished"] = time.time()
                if error is None:
                    job["status"], job["result"] = "done", result
                    self.cache[job["key"]] = result
                    while len(self.cache) > self.cache_size:
                        self.cache.popitem(last=False)
                else:
                    job["status"], job["error"] = "failed", str(error)

    def _forget_old(self):
        cutoff = time.time() - self.keep_s
        for jid in [j for j, job in self.jobs.items() if job.get("finished", time.time()) < cutoff]:
            del self.jobs[jid]
