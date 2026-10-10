"""Tests for api/jobs.py — the explanation waiting line. Run:  python -m unittest api.test_jobs -v"""
import threading, time, unittest

from api.jobs import Line, LineFull


def wait_done(line, jid, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        t = line.view(jid)
        if t["status"] in ("done", "failed"):
            return t
        time.sleep(0.01)
    raise AssertionError("job did not finish")


class TheLine(unittest.TestCase):
    def test_one_at_a_time_in_arrival_order(self):
        order, gate = [], threading.Event()
        def work(x):
            gate.wait(); order.append(x); return x * 10
        line = Line(work)
        a, b, c = (line.submit(k, v)["job_id"] for k, v in (("a", 1), ("b", 2), ("c", 3)))
        time.sleep(0.05)
        self.assertEqual(line.view(a)["status"], "running")
        self.assertEqual((line.view(b)["position"], line.view(c)["position"]), (1, 2))   # explanations ahead
        gate.set()
        self.assertEqual(wait_done(line, c)["result"], 30)
        self.assertEqual(order, [1, 2, 3])

    def test_same_complaint_shares_a_job_then_comes_from_the_cache(self):
        calls, gate = [], threading.Event()
        def work(x):
            gate.wait(); calls.append(x); return x
        line = Line(work)
        first = line.submit("same", 7)["job_id"]
        self.assertEqual(line.submit("same", 7)["job_id"], first)       # while waiting: the same ticket
        gate.set(); wait_done(line, first)
        again = line.submit("same", 7)
        self.assertEqual((again["status"], again["result"]), ("done", 7))   # finished before: instant
        self.assertEqual(calls, [7])                                    # worked out only once

    def test_full_line_says_so(self):
        gate = threading.Event()
        line = Line(lambda x: gate.wait(), max_waiting=2)
        line.submit("k0", 0); time.sleep(0.05)                          # running — not waiting
        line.submit("k1", 1); line.submit("k2", 2)
        with self.assertRaises(LineFull):
            line.submit("k3", 3)
        gate.set()

    def test_a_failure_is_reported_and_the_line_keeps_going(self):
        def work(x):
            if x == "bad":
                raise RuntimeError("broken")
            return "fine"
        line = Line(work)
        bad, good = line.submit("b", "bad")["job_id"], line.submit("g", "good")["job_id"]
        self.assertIn("broken", wait_done(line, bad)["error"])
        self.assertEqual(wait_done(line, good)["result"], "fine")


if __name__ == "__main__":
    unittest.main()
