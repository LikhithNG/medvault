#!/usr/bin/env python3
"""Produce the things a person actually ends up holding.

Run from the project root:  python3 tools/make_outputs.py

Assignment 4 draws a line between an output and intermediate data: raw JSON out of a
model is not an output, a letter somebody can put in front of a billing office is. This
runs all seven sample bills through the same code the Bill screen runs - the same parser,
the same Checker, the same rights evaluation, the same letter builder - and writes what
comes out into outputs/.

Nothing here is written by hand or by a model. Every figure in every file traces to the
hospital's own published price file, and any line that could not carry a complete receipt
is withheld and says so.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

import billchecks   # noqa: E402
import checker      # noqa: E402
import dispute      # noqa: E402
import medicare     # noqa: E402
import paste        # noqa: E402
import receipts     # noqa: E402
import rights       # noqa: E402

SAMPLES = ROOT / "samples" / "bills"
OUT = ROOT / "outputs"
# The sample bills are written on this hospital's published prices; see tools/make_sample_bills.py.
HOSPITAL = "Doylestown Hospital"


def money(v):
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "—"


def findings_report(name, bill_text, reviewed, face, protections, bench):
    """The screen, as a page. What was checked, what it found, and what it could not say."""
    lines = reviewed["lines"]
    flagged = [l for l in lines if l["verdict"] != "VERIFIED"]
    out = [f"MedVault — what the checks found on {name}",
           "=" * 70, "",
           f"Hospital           {HOSPITAL}",
           f"Lines read         {len(lines)}",
           f"Billed total       {money(reviewed.get('billed_total'))}",
           f"Published total    {money(reviewed.get('posted_total'))}",
           f"Unexplained gap    {money(reviewed.get('questionable_amount'))}",
           "",
           "This gap is a question to ask, not money owed back and not a refund estimate.",
           "", "Checked against the hospital's own published prices", "-" * 70]

    if not flagged:
        out.append("  Every line matches the price this hospital publishes. Nothing to raise.")
    for l in flagged:
        out.append(f"  {l.get('code') or '—':<8} {(l.get('description') or '')[:40]:<42}"
                   f"{money(l.get('charged')):>12}")
        out.append(f"           verdict: {l['verdict']} — {l['reason']}")
        r = receipts.receipt(l)
        if r:
            out.append(f"           receipt: {r['basis']}, collected {r['collected_date']}")
            out.append(f"                    {r['source_url']}")
        out.append("")

    out += ["Wrong on the bill's own face", "-" * 70]
    out += [f"  line {i + 1}: {f['title']} — {f['detail']}" for i, f in face] or \
           ["  Nothing. The arithmetic adds up and no code is unspecified."]

    out += ["", "Against the national Medicare allowance", "-" * 70]
    any_bench = False
    for l in lines:
        b = bench.get((l.get("code") or "").upper())
        if not b or not b.get("medicare_rate"):
            continue
        any_bench = True
        mult = medicare.multiple_of_medicare(l.get("charged"), l.get("units"),
                                             b["medicare_rate"])
        out.append(f"  {l['code']:<8} {b['name'][:40]:<42}{money(l.get('charged')):>12}")
        out.append(f"           Medicare allows {money(b['medicare_rate'])}"
                   + (f" — {mult:g}x" if mult else "")
                   + f"   (CMS {b.get('dataset','')} {b.get('effective_year','')})")
    if not any_bench:
        out.append("  No code on this bill is in the national fee schedule.")
    out += ["", "A Medicare rate is not a price cap. A hospital may charge a commercial",
            "patient more, and usually does.", ""]

    out += ["What the law may already give you", "-" * 70]
    out += [f"  {f['title']}\n           {f['todo']}\n           ({f['source']})"
            for f in protections] or ["  Nothing was established — the questions that"
                                      " decide this were left unanswered."]

    audit = receipts.audit(reviewed)
    out += ["", "Receipt audit", "-" * 70,
            f"  {len(audit)} line(s) assert a dollar comparison without a complete receipt."
            if audit else
            "  Every line that asserts a dollar comparison carries a complete receipt."]
    return "\n".join(out) + "\n"


def main():
    OUT.mkdir(exist_ok=True)
    table = checker.load_reference()
    written, index = [], []

    for path in sorted(SAMPLES.glob("*.txt")):
        name = path.stem
        text = path.read_text()
        lines = paste.lines(text)
        reviewed = checker.check_bill({"hospital_name": HOSPITAL, "line_items": lines},
                                      table)
        face = billchecks.run(reviewed["lines"])
        ctx = rights.context()
        protections = rights.evaluate(reviewed["lines"],
                                      reviewed.get("billed_total") or 0, ctx)
        bench = medicare.lookup_many([l.get("code") for l in reviewed["lines"]])

        report = OUT / f"{name}_findings.txt"
        report.write_text(findings_report(name, text, reviewed, face, protections, bench))
        written.append(report)

        letter = OUT / f"{name}_letter.txt"
        letter.write_text(dispute.letter(
            reviewed, patient_name="A. Patient", rights_findings=protections))
        written.append(letter)

        flagged = sum(1 for l in reviewed["lines"] if l["verdict"] != "VERIFIED")
        index.append((name, len(reviewed["lines"]), flagged,
                      reviewed.get("questionable_amount") or 0,
                      len(receipts.audit(reviewed))))

    readme = ["MedVault — sample outputs", "=" * 70, "",
              "Generated by tools/make_outputs.py from the seven synthetic bills in",
              "samples/bills/, through the same code the Bill screen runs. Two files per",
              "bill: what the checks found, and the letter built from those findings.",
              "", "Nothing here was written by a model. Every figure traces to Doylestown",
              "Hospital's published standard-charge file, collected 2 October 2026.", "",
              f"{'bill':<28}{'lines':>6}{'flagged':>9}{'unexplained':>14}{'no receipt':>12}",
              "-" * 70]
    for name, n, flagged, gap, missing in index:
        readme.append(f"{name:<28}{n:>6}{flagged:>9}{money(gap):>14}{missing:>12}")
    readme += ["", f"{len(written)} files.",
               "'no receipt' is the count of lines asserting a dollar comparison without",
               "a complete receipt. It must be zero everywhere."]
    (OUT / "README.txt").write_text("\n".join(readme) + "\n")

    print("\n".join(readme))
    print(f"\nwrote {len(written) + 1} files to {OUT}")


if __name__ == "__main__":
    main()
