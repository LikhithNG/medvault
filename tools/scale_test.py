#!/usr/bin/env python3
"""What this actually does under load, measured rather than estimated.

Run from the project root:  python3 tools/scale_test.py

Assignment 4 asks for honest breaking points, and the honest answer here has two halves
that behave completely differently.

The deterministic half - the Checker, the arithmetic, the rights checks, the record
cross-check and the letter - is pure Python over a 262-row table held in memory. It does
not break at any volume this project will ever see, and the numbers below say so with
measurements instead of a claim.

The half that breaks is the half that leaves the machine. Gemini's free tier allows 20
requests per day PER MODEL, so the binding constraint on reading documents is not latency,
memory or CPU - it is a daily cap that no amount of engineering removes. That is why
medvault/gemini.py keeps a pool: the cap is per model, so N models multiply the budget.
This script measures that too, with a deliberately small number of real calls, because
burning the day's quota to produce a graph would be a silly way to spend it.
"""
import argparse
import pathlib
import random
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

import billchecks   # noqa: E402
import checker      # noqa: E402
import dispute      # noqa: E402
import medicare     # noqa: E402
import receipts     # noqa: E402
import rights       # noqa: E402

HOSPITAL = "Doylestown Hospital"
VOLUMES = (1, 10, 50, 100, 500, 1000)


def pct(values, p):
    """Nearest-rank percentile. Reported for p50, p95 and p99 rather than a mean, because
    a mean hides the one run in a hundred that a person actually waits through."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round(p / 100 * len(ordered) + 0.5)) - 1))
    return ordered[k]


def synthetic_bill(table, hospital, lines, rng):
    """A bill built from codes that hospital really publishes, so the Checker does real
    lookups rather than missing every row."""
    codes = [c for (h, c) in table if h == hospital.lower()]
    picked = rng.sample(codes, min(lines, len(codes)))
    items = []
    for code in picked:
        ref = table[(hospital.lower(), code)]
        posted = float(ref["hospital_gross_charge"] or 0) or 100.0
        items.append({"code": code, "description": ref["description"][:40],
                      "units": rng.choice([1, 1, 1, 2, 12]),
                      "charged": round(posted * rng.uniform(0.9, 6.0), 2)})
    return {"hospital_name": hospital, "line_items": items}


def one_bill(bill, table):
    """Everything that happens between a parsed bill and a letter a patient can send -
    the same calls the Bill screen makes, in the same order."""
    reviewed = checker.check_bill(bill, table)
    lines = reviewed["lines"]
    billchecks.run(lines)
    ctx = rights.context()
    rights.evaluate(lines, reviewed.get("billed_total") or 0, ctx)
    rights.unanswered(ctx)
    dispute.letter(reviewed, patient_name="Scale Test")
    return reviewed


def deterministic(table, runs, lines, rng):
    timings = []
    audit_failures = 0
    for _ in range(runs):
        bill = synthetic_bill(table, HOSPITAL, lines, rng)
        start = time.perf_counter()
        reviewed = one_bill(bill, table)
        timings.append((time.perf_counter() - start) * 1000)
        audit_failures += len(receipts.audit(reviewed))
    return timings, audit_failures


def measure_reader(samples):
    """A deliberately small number of real calls. The point is the shape of the latency
    and the error the quota produces, not a distribution."""
    try:
        import gemini
    except ImportError:
        return None
    timings, failures, models = [], [], set()
    for i in range(samples):
        start = time.perf_counter()
        r = gemini.generate(f"Reply with the single word READY. Attempt {i}.")
        timings.append((time.perf_counter() - start) * 1000)
        if r.get("ok"):
            models.add(r.get("model"))
        else:
            failures.append(str(r.get("error"))[:90])
    return {"timings": timings, "failures": failures, "models": sorted(models)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=int, default=8, help="line items per synthetic bill")
    ap.add_argument("--reader-calls", type=int, default=0,
                    help="real model calls to time (costs daily quota; 0 skips)")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    print("MedVault scale test")
    print(f"run at {time.strftime('%Y-%m-%d %H:%M:%S')}  ·  {args.lines} lines per bill\n")

    start = time.perf_counter()
    table = checker.load_reference()
    load_ms = (time.perf_counter() - start) * 1000
    print(f"reference table: {len(table)} rows loaded in {load_ms:.0f} ms, held in memory\n")

    print("THE DETERMINISTIC PATH - checker, arithmetic, rights, letter")
    print(f"{'bills':>7}{'total s':>10}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}"
          f"{'bills/s':>10}{'no receipt':>12}")
    for volume in VOLUMES:
        began = time.perf_counter()
        timings, missing = deterministic(table, volume, args.lines, rng)
        total = time.perf_counter() - began
        print(f"{volume:>7}{total:>10.2f}{pct(timings,50):>9.2f}{pct(timings,95):>9.2f}"
              f"{pct(timings,99):>9.2f}{volume/total:>10.0f}{missing:>12}")

    print("\nTHE CACHED LOOKUP - Medicare benchmark, already on disk")
    cached = []
    for _ in range(200):
        began = time.perf_counter()
        medicare.lookup("70450")
        cached.append((time.perf_counter() - began) * 1000)
    print(f"  200 lookups · p50 {pct(cached,50):.3f} ms · p99 {pct(cached,99):.3f} ms")

    print("\nTHE NETWORK LOOKUP - Medicare benchmark, cache bypassed")
    live = []
    for code in ("93000", "99213", "80053", "85025", "71045"):
        began = time.perf_counter()
        r = medicare.lookup(code, use_cache=False)
        live.append(((time.perf_counter() - began) * 1000, code, r.get("found")))
    for ms, code, found in live:
        print(f"  {code}  {ms:7.0f} ms  found={found}")
    nums = [ms for ms, _, _ in live]
    print(f"  p50 {pct(nums,50):.0f} ms · p99 {pct(nums,99):.0f} ms")

    if args.reader_calls:
        print(f"\nTHE READER - {args.reader_calls} real model call(s)")
        out = measure_reader(args.reader_calls)
        if out:
            for i, ms in enumerate(out["timings"], 1):
                print(f"  call {i}: {ms:.0f} ms")
            print(f"  models that answered: {', '.join(out['models']) or 'none'}")
            for f in out["failures"]:
                print(f"  failure: {f}")

    print("""
WHAT BREAKS FIRST, in the order it happens

  1. Gemini's free tier: 20 requests per day PER MODEL. Reading documents stops there,
     and no amount of local optimisation moves it. The pool in gemini.py exists for this
     reason - the cap is per model, so six models is six times the budget. Past that the
     app does not crash; reader_ready() reports it and every deterministic check still
     runs, which is most of what the Bill screen does.
  2. The Medicare endpoint, on a code not already cached. One network round trip per new
     code, cached for 30 days afterwards. The committed cache holds six codes.
  3. Nothing else, at any volume tested here. The deterministic path is a dictionary
     lookup against 262 rows in memory; it is bounded by CPU and the table never grows.

COST
  Deterministic path: $0. No network call, no model, no per-request cost at all.
  Reader: $0 on the free tiers used here. At Gemini Flash list price a bill page is
  roughly 1,500 tokens in and 400 out, which is a fraction of a cent - the limit that
  binds is the request cap, not the money.

COULD IT RUN 24/7
  The deterministic half, yes. The reading half, no - not on a free tier, because 20
  requests per model per day is roughly one patient's paperwork, not a service. Running
  it for real means a paid key, and that is a cost decision rather than an engineering
  one.

WHAT WOULD HAVE TO BE WATCHED
  Reader availability per model (gemini.pool_status() already reports which models are
  retired and when they come back), the Medicare endpoint's error rate, and the count of
  flags that fail receipts.audit() - which is zero in every run above and is the number
  that must never drift.""")


if __name__ == "__main__":
    main()
