#!/usr/bin/env python3
"""Running an agent: timed, classified, held to its budget, and recorded - without
recording anything it read.

Before this, an agent run left no trace. A Companion answer took 46 seconds and there was
no way to say whether that was one slow model, a retry, or the pool falling through three
models in turn; a Reader failure was a sentence on one patient's screen and gone. An AI
system that cannot say how its agents behaved in use cannot be improved on evidence.

So every agent a person starts runs inside span(). The span measures it, notes which
model answered and how many attempts it took, sorts any failure into one of a few kinds,
and - when given a connection - writes one row to agent_runs.

**What the row holds is the point.** Agent, when, how long, whether it worked, the model,
the attempt count, the kind of failure. Not the account, not the question, not the
answer, not a word of any record, and not the provider's raw error text, which can echo
part of the request. The trace exists to tune budgets and spot a failing provider; none of
that needs to know whose bill it was, and a health app should not keep what it does not
need.
"""
import contextlib
import logging
import statistics
import time
from dataclasses import dataclass

import agents

log = logging.getLogger("medvault.runtime")

# How many rows the trace keeps. Enough for a percentile to mean something, small enough
# never to matter to the database.
KEEP = 5000

# The table is in db.SCHEMA, with the rest of the vault's layout.

# Failure kinds, in the order they are tested. A kind is what an operator acts on:
# "timeout" means raise the budget or change provider, "quota" means wait or pay,
# "malformed" means the prompt or schema, "refused" means the input.
KINDS = (
    ("timeout", ("timed out", "timeout", "deadline", "out of time")),
    ("quota", ("429", "resource_exhausted", "quota", "rate limit")),
    ("overloaded", ("503", "502", "500", "unavailable", "overloaded")),
    ("malformed", ("malformed", "did not return", "jsondecode", "not json")),
    ("network", ("urlerror", "connection", "name or service", "ssl", "oserror")),
    ("not_configured", ("not set", "not configured", "api_key")),
    ("refused", ("no charges", "no billing codes", "nothing to read")),
)


def classify(error):
    """The kind of a failure, from whatever text described it. Never the text itself."""
    text = str(error or "").lower()
    for kind, needles in KINDS:
        if any(n in text for n in needles):
            return kind
    return "other"


@dataclass(frozen=True)
class Run:
    agent: str
    started_at: float
    seconds: float
    ok: bool
    model: str | None = None
    attempts: int | None = None
    error_kind: str | None = None
    over_budget: bool = False


class _Span:
    """What the caller can say about a run while it is happening. Turned into a frozen
    Run when the run ends; never stored itself."""

    def __init__(self, agent):
        self.agent = agent
        self.started_at = time.time()
        self._t0 = time.perf_counter()
        self.ok = True
        self.model = None
        self.attempts = None
        self.error_kind = None

    @property
    def budget(self):
        return agents.BY_NAME[self.agent]["budget_s"]

    def left(self):
        """Seconds of the budget still unspent - what a model call should be given."""
        return max(0.0, self.budget - (time.perf_counter() - self._t0))

    def saw(self, result):
        """Take ok / model / attempts / error from a model client's or agent's result."""
        if isinstance(result, dict):
            if result.get("model"):
                self.model = result["model"]
            if result.get("attempts") is not None:
                self.attempts = result["attempts"]
            if result.get("ok") is False or result.get("kind") == "error":
                self.fail(result.get("error"))
        return result

    def fail(self, error):
        self.ok = False
        self.error_kind = classify(error)

    def finish(self):
        seconds = time.perf_counter() - self._t0
        return Run(agent=self.agent, started_at=self.started_at, seconds=seconds,
                   ok=self.ok, model=self.model, attempts=self.attempts,
                   error_kind=self.error_kind, over_budget=seconds > self.budget)


@contextlib.contextmanager
def span(agent, trace=None, done=None):
    """Run the body as one run of `agent`.

        with runtime.span("Companion", trace=con) as s:
            reply = ask.answer(con, me, q, deadline=s.left())
            s.saw(reply)

    An exception inside is recorded as a failed run and raised again, unchanged: the
    trace observes failures, it does not absorb them. `done`, if given, is called with
    the finished Run - the interface uses it to say how long the agent took.
    """
    if agent not in agents.BY_NAME:
        raise KeyError(f"{agent} is not a registered agent")
    s = _Span(agent)
    try:
        yield s
    except Exception as problem:
        s.fail(f"{type(problem).__name__}: {problem}")
        raise
    finally:
        run = s.finish()
        if trace is not None and agents.BY_NAME[agent]["traced"]:
            record(trace, run)
        if done is not None:
            done(run)


def record(con, run):
    """Write one run. A trace that cannot be written must never cost the patient the
    answer it was tracing, so a failure here is logged and the run goes on."""
    try:
        cur = con.execute(
            "INSERT INTO agent_runs (agent, started_at, seconds, ok, model, attempts,"
            " error_kind, over_budget) VALUES (?,?,?,?,?,?,?,?)",
            (run.agent, run.started_at, round(run.seconds, 4), int(run.ok), run.model,
             run.attempts, run.error_kind, int(run.over_budget)))
        if (cur.lastrowid or 0) % 100 == 0:
            con.execute("DELETE FROM agent_runs WHERE id <= ?", (cur.lastrowid - KEEP,))
        con.commit()
    except Exception as problem:            # noqa: BLE001 - logged, and the run goes on
        log.warning("agent trace not written for %s: %s", run.agent, problem)


def _percentile(values, q):
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[q - 1]


def summary(con, last=KEEP):
    """Per agent, over the most recent runs: how many, how often they worked, how long
    they took (median and 95th percentile), how often they ran over budget, and the most
    recent kind of failure. For the diagnostics screen and for setting budgets."""
    rows = con.execute(
        "SELECT agent, seconds, ok, model, error_kind, over_budget, started_at"
        " FROM agent_runs ORDER BY id DESC LIMIT ?", (last,)).fetchall()
    out = {}
    for r in rows:
        out.setdefault(r["agent"], []).append(dict(r))
    report = []
    for agent in agents.BY_NAME:
        runs = out.get(agent, [])
        if not runs:
            continue
        times = sorted(r["seconds"] for r in runs)
        failures = [r for r in runs if not r["ok"]]
        report.append({
            "agent": agent, "runs": len(runs),
            "ok_rate": round(1 - len(failures) / len(runs), 3),
            "p50": round(_percentile(times, 50), 3),
            "p95": round(_percentile(times, 95), 3),
            "budget_s": agents.BY_NAME[agent]["budget_s"],
            "over_budget": sum(r["over_budget"] for r in runs),
            "last_failure": failures[0]["error_kind"] if failures else None,
            "models": sorted({r["model"] for r in runs if r["model"]}),
        })
    return report
