#!/usr/bin/env python3
"""Measure the two Assignment 2 metrics that were never measured.

Run from the project root:
    python3 tools/accuracy_test.py                 # 50 bills, no model calls
    python3 tools/accuracy_test.py --bills 200
    python3 tools/accuracy_test.py --reader 2 --write

The PRD promised >=90% precision on overcharge flags against 50 hand-labelled bills, and
>=85% extraction accuracy on code and amount against hand transcription of the same ones.
Neither number existed. These are those numbers.

WHERE THE LABELS COME FROM, because this is the part that decides whether the result
means anything.

They are not hand-labelled. They are labelled BY CONSTRUCTION: a line is built as "this
code, at 3.4x the price Doylestown publishes for it, 1 unit", so what that line is, is a
fact about how it was made rather than a judgement somebody recorded. That is stronger
than hand-labelling for the thing being measured here, and weaker in a way that has to be
said out loud:

  * It measures whether the Checker agrees with the published table. It does NOT measure
    whether the table is right, and it does NOT measure whether a billing office would
    agree. A hospital may have republished since 2 October 2026.
  * The expected verdict is computed below from the DOCUMENTED rules, restated here in
    full rather than imported from checker.py. If somebody changes TOLERANCE or
    UNIT_SUSPICION, this harness disagrees with the implementation and the disagreement
    is the finding. Importing the constants would make the test agree with any change,
    which is a test that cannot fail.

What that combination does catch, and what makes it worth running: a lookup against the
wrong hospital, cash price used where gross charge was meant, a quantity ignored, a code
matched loosely, a verdict precedence applied in the wrong order. The quantity bug this
project actually shipped - two units at $50 read as one and reported as $50 over, in a
letter - is exactly this class, and this harness fails on it.
"""
import argparse
import json
import math
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

import checker   # noqa: E402
import paste     # noqa: E402

BENCH = ROOT / "bench"

# The documented rules, restated. Deliberately not imported - see the module docstring.
TOLERANCE = 1.01          # a 1% rounding allowance before a line counts as over
UNIT_SUSPICION = 10       # quantities at or above this on a once-per-visit code
ONCE_PER_VISIT = {"99281", "99282", "99283", "99284", "99285",
                  "70450", "70486", "71046", "72148", "74177", "G0378", "G0379"}
# Verdict precedence, in the order the Checker is specified to apply it.
PRECEDENCE = ("UNREADABLE", "DUPLICATE", "NOT_POSTED", "QUANTITY_SUSPECT",
              "ABOVE_POSTED", "VERIFIED")


def wilson(hits, total, z=1.96):
    """A 95% confidence interval for a proportion. Wilson rather than the normal
    approximation because at 50 bills the sample is small and near 1.0, which is exactly
    where the normal approximation returns an upper bound above 100%."""
    if not total:
        return 0.0, 0.0
    p = hits / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def by_hospital(table):
    """Every hospital's own price list, keyed by the name as the table spells it.

    The corpus spans all nine on purpose. A first version used Doylestown alone, and
    Doylestown is one of only two hospitals here whose gross charge and cash price are
    identical on every row - so a mutation that compared against the wrong basis was
    invisible, and the benchmark reported 100% while silently unable to detect it. Seven
    of the nine differ.
    """
    out = {}
    for (h, code), row in table.items():
        out.setdefault(row["hospital_name"], {})[code] = row
    return out


def build_bill(rng, hospital, prices, unpublished, index):
    """One bill, every line carrying the label it was built with."""
    codes = sorted(prices)
    lines, used = [], set()

    def posted_for(code):
        return float(prices[code]["hospital_gross_charge"] or 0) or 100.0

    plan = ["at_published", "above_published", "above_published"]
    plan += rng.sample(["at_published", "duplicate", "quantity", "not_posted",
                        "above_published", "just_inside_tolerance"],
                       rng.randint(2, 4))
    rng.shuffle(plan)

    for label in plan:
        if label == "not_posted":
            code = rng.choice(unpublished)
            lines.append({"code": code, "description": f"ITEM {code}", "units": 1,
                          "charged": round(rng.uniform(80, 900), 2), "label": label,
                          "posted": None, "multiple": None})
            continue

        if label == "duplicate" and used:
            code = rng.choice(sorted(used))
        else:
            remaining = [c for c in codes if c not in used]
            if not remaining:
                continue
            code = rng.choice(remaining)
        posted = posted_for(code)

        if label == "quantity":
            code = rng.choice([c for c in ONCE_PER_VISIT if c in prices] or [code])
            posted = posted_for(code)
            units, multiple = rng.randint(UNIT_SUSPICION, 24), 1.0
        elif label == "above_published":
            units, multiple = rng.choice([1, 1, 2]), round(rng.uniform(1.4, 6.0), 3)
        elif label == "just_inside_tolerance":
            units, multiple = 1, 1.005        # inside the documented 1% allowance
        else:
            units, multiple = rng.choice([1, 1, 2]), 1.0

        lines.append({"code": code, "description": prices[code]["description"][:38],
                      "units": units, "charged": round(posted * units * multiple, 2),
                      "label": label, "posted": posted, "multiple": multiple})
        used.add(code)

    return {"id": f"bench_{index:03d}", "hospital_name": hospital, "line_items": lines}


def expected_verdict(line, seen_codes, prices):
    """What the documented rules say this line is, in the documented order."""
    if line["charged"] is None:
        return "UNREADABLE"
    # The same code again on the same day. Every benchmark bill is a single undated visit,
    # so here that is the code appearing again.
    if line["code"] in seen_codes:
        return "DUPLICATE"
    if line["code"] not in prices:
        return "NOT_POSTED"
    if line["units"] >= UNIT_SUSPICION and line["code"] in ONCE_PER_VISIT:
        return "QUANTITY_SUSPECT"
    expected_total = float(prices[line["code"]]["hospital_gross_charge"] or 0) * line["units"]
    if expected_total and line["charged"] > expected_total * TOLERANCE:
        return "ABOVE_POSTED"
    return "VERIFIED"


def label_corpus(corpus, catalogue):
    for bill in corpus:
        seen, prices = set(), catalogue[bill["hospital_name"]]
        for line in bill["line_items"]:
            line["expect"] = expected_verdict(line, seen, prices)
            seen.add(line["code"])
    return corpus


def render(bill):
    """The bill as a patient would see it, and paste in."""
    out = [bill["hospital_name"].upper(), "Patient Financial Services    Account 00000000",
           "*** SYNTHETIC BENCHMARK BILL - NOT A REAL STATEMENT ***", "",
           "DATE        CODE    DESCRIPTION                      QTY       AMOUNT"]
    total = 0.0
    for line in bill["line_items"]:
        total += line["charged"] or 0
        out.append(f"2026-03-14  {line['code']:<7} {line['description'][:30]:<32}"
                   f"{line['units']:>3}{line['charged']:>13,.2f}")
    out += ["", f"{'TOTAL DUE':>58}{total:>13,.2f}"]
    return "\n".join(out)


def measure_flagging(corpus, table, catalogue=None):
    """Precision and recall on the overcharge flag, and the full confusion."""
    confusion, flagged_right, flagged_total, truly_over, caught = {}, 0, 0, 0, 0
    for bill in corpus:
        reviewed = checker.check_bill(
            {"hospital_name": bill["hospital_name"],
             "line_items": [{k: l[k] for k in ("code", "description", "units", "charged")}
                            for l in bill["line_items"]]}, table)
        for line, got in zip(bill["line_items"], reviewed["lines"]):
            key = (line["expect"], got["verdict"])
            confusion[key] = confusion.get(key, 0) + 1
            if got["verdict"] == "ABOVE_POSTED":
                flagged_total += 1
                flagged_right += line["expect"] == "ABOVE_POSTED"
            if line["expect"] == "ABOVE_POSTED":
                truly_over += 1
                caught += got["verdict"] == "ABOVE_POSTED"
    return confusion, flagged_right, flagged_total, caught, truly_over


def measure_extraction(corpus):
    """Code and amount recovered from the rendered page by the deterministic parser.
    Both fields must be right for the line to count, as the PRD specified."""
    lines_total = both_right = code_right = amount_right = 0
    for bill in corpus:
        parsed = paste.lines(render(bill))
        truth = bill["line_items"]
        for i, want in enumerate(truth):
            lines_total += 1
            got = parsed[i] if i < len(parsed) else {}
            c = (got.get("code") or "") == want["code"]
            a = got.get("charged") == want["charged"]
            code_right += c
            amount_right += a
            both_right += c and a
    return lines_total, both_right, code_right, amount_right


def measure_reader(corpus, n):
    """The same measurement against the model reader, on a deliberately small sample:
    Gemini's free tier is 20 requests per day per model."""
    import extract
    lines_total = both_right = 0
    failures = []
    for bill in corpus[:n]:
        # read_bill_verified returns (lines, meta) - the lines directly, not a wrapper.
        got, meta = extract.read_bill_verified(text=render(bill))
        if not meta.get("ok"):
            failures.append(str(meta.get("error"))[:80])
            continue
        if meta.get("reconciled") is False:
            failures.append(f"{bill['id']}: did not reconcile against the printed total")
        for i, want in enumerate(bill["line_items"]):
            lines_total += 1
            g = got[i] if i < len(got) else {}
            if (str(g.get("code") or "") == want["code"]
                    and abs((g.get("charged") or -1) - want["charged"]) < 0.005):
                both_right += 1
    return lines_total, both_right, failures


# ---- proving the benchmark can fail -----------------------------------------
# A 100% result is only worth reading if the measurement could have produced anything
# else. Each mutation below re-introduces a real defect - three of them are bugs this
# project actually shipped or nearly did - and the benchmark has to notice. The first
# version of this corpus used one hospital, and that hospital is one of only two here
# whose gross charge and cash price are identical, so MUTATIONS["basis"] passed silently
# at 100%. That is how this mode earned its place.

def _mutations():
    original = checker.check_line

    def units_ignored(item, hospital, table, seen):
        """The bug that shipped: two units at $50 read as one, and the letter said the
        line was $50 over."""
        return original({**item, "units": 1}, hospital, table, seen)

    def wrong_basis(item, hospital, table, seen):
        """Cash price compared where the gross charge was meant. The PRD calls this out
        by name: comparing against the wrong basis manufactures a fake overcharge."""
        key = (hospital.strip().lower(), str(item.get("code", "")).strip())
        ref = table.get(key)
        if ref:
            table = {**table, key: {**ref,
                                    "hospital_gross_charge": ref["hospital_cash_price"]}}
        return original(item, hospital, table, seen)

    def wrong_hospital(item, hospital, table, seen):
        """Every bill priced against one hospital's file regardless of who sent it."""
        return original(item, "Doylestown Hospital", table, seen)

    return original, {"units": units_ignored, "basis": wrong_basis,
                      "hospital": wrong_hospital}


def run_mutations(corpus, table):
    original, muts = _mutations()
    rows = []
    try:
        for name, fn in [("none (as shipped)", original)] + list(muts.items()):
            checker.check_line = fn
            conf, right, total, caught, truly = measure_flagging(corpus, table)
            rows.append((name, right / total if total else 0.0,
                         caught / truly if truly else 0.0,
                         sum(v for k, v in conf.items() if k[0] != k[1])))
        checker.check_line = original
        widened = checker.TOLERANCE
        checker.TOLERANCE = 2.0
        conf, right, total, caught, truly = measure_flagging(corpus, table)
        rows.append(("tolerance widened to 2.0x", right / total if total else 0.0,
                     caught / truly if truly else 0.0,
                     sum(v for k, v in conf.items() if k[0] != k[1])))
        checker.TOLERANCE = widened
    finally:
        checker.check_line = original
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bills", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20261026)
    ap.add_argument("--reader", type=int, default=0,
                    help="bills to send to the model reader (costs daily quota)")
    ap.add_argument("--write", action="store_true", help="write the corpus to bench/")
    ap.add_argument("--mutate", action="store_true",
                    help="re-introduce known defects and check the benchmark notices")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    table = checker.load_reference()
    catalogue = by_hospital(table)
    hospitals = sorted(catalogue)
    every_code = {c for (_, c) in table}

    corpus = []
    for i in range(args.bills):
        hospital = hospitals[i % len(hospitals)]
        prices = catalogue[hospital]
        unpublished = sorted(every_code - set(prices))
        corpus.append(build_bill(rng, hospital, prices, unpublished, i))
    corpus = label_corpus(corpus, catalogue)
    all_lines = [l for b in corpus for l in b["line_items"]]

    print(f"MedVault accuracy benchmark · {args.bills} bills · seed {args.seed}")
    print(f"{len(all_lines)} lines across {len(hospitals)} hospitals, labelled by "
          f"construction against each one's own published file\n")
    counts = {}
    for l in all_lines:
        counts[l["expect"]] = counts.get(l["expect"], 0) + 1
    print("  ground truth: " + " · ".join(f"{k} {v}" for k, v in
                                          sorted(counts.items(), key=lambda kv: -kv[1])))

    confusion, right, total, caught, truly = measure_flagging(corpus, table)
    precision = right / total if total else 0.0
    recall = caught / truly if truly else 0.0
    lo, hi = wilson(right, total)
    rlo, rhi = wilson(caught, truly)

    print("\nMETRIC 1 — precision of the overcharge flag   (PRD target: >=90%)")
    print(f"  flagged ABOVE_POSTED : {total}")
    print(f"  of those, truly over : {right}")
    print(f"  precision            : {precision:.1%}   95% CI [{lo:.1%}, {hi:.1%}]")
    print(f"  recall               : {recall:.1%}   95% CI [{rlo:.1%}, {rhi:.1%}]"
          f"   ({caught}/{truly})")
    print("  precision is the one that governs: telling somebody to dispute a legitimate")
    print("  charge sends them into a fight they lose.")

    wrong = {k: v for k, v in confusion.items() if k[0] != k[1]}
    print(f"\n  disagreements with the documented rules: {sum(wrong.values())}")
    for (want, got), n in sorted(wrong.items(), key=lambda kv: -kv[1]):
        print(f"    expected {want:<17} got {got:<17} {n}")

    n, both, code_ok, amt_ok = measure_extraction(corpus)
    blo, bhi = wilson(both, n)
    print("\nMETRIC 2 — extraction accuracy, code AND amount   (PRD target: >=85%)")
    print(f"  lines              : {n}")
    print(f"  code correct       : {code_ok} ({code_ok/n:.1%})")
    print(f"  amount correct     : {amt_ok} ({amt_ok/n:.1%})")
    print(f"  both correct       : {both} ({both/n:.1%})   95% CI [{blo:.1%}, {bhi:.1%}]")
    print("  measured on the deterministic parser reading the rendered page.")

    if args.reader:
        rn, rboth, failures = measure_reader(corpus, args.reader)
        print(f"\nMETRIC 2b — the model reader, {args.reader} bill(s)")
        if rn:
            flo, fhi = wilson(rboth, rn)
            print(f"  lines {rn} · both correct {rboth} ({rboth/rn:.1%})"
                  f"   95% CI [{flo:.1%}, {fhi:.1%}]")
        for f in failures:
            print(f"  failure: {f}")
        print("  a small sample on purpose: 20 requests per day per model.")

    if args.mutate:
        print("\nMUTATION CHECK — can this benchmark fail?")
        print(f"  {'defect introduced':<30}{'precision':>11}{'recall':>9}"
              f"{'disagree':>10}  verdict")
        for name, prec, rec, wrong in run_mutations(corpus, table):
            shipped = name.startswith("none")
            ok = (wrong == 0) if shipped else (wrong > 0)
            note = "clean" if shipped else ("caught" if wrong else "MISSED")
            print(f"  {name:<30}{prec:>10.1%}{rec:>9.1%}{wrong:>10}  {note}")
        print("  a benchmark that cannot fail is not a measurement.")

    if args.write:
        BENCH.mkdir(exist_ok=True)
        (BENCH / "corpus.json").write_text(json.dumps(
            {"generated_with": f"tools/accuracy_test.py --bills {args.bills} "
                               f"--seed {args.seed}",
             "labels": "by construction, not by hand - see the module docstring",
             "hospitals": hospitals,
             "reference_collected": "2026-10-02",
             "bills": corpus}, indent=1) + "\n")
        for bill in corpus[:5]:
            (BENCH / f"{bill['id']}.txt").write_text(render(bill) + "\n")
        print(f"\nwrote bench/corpus.json and 5 rendered bills")

    ok = precision >= 0.90 and both / n >= 0.85
    print(f"\n{'BOTH TARGETS MET' if ok else 'A TARGET WAS MISSED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
