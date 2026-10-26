#!/usr/bin/env python3
"""Build sample bills that each trip a specific check, as text and as photographs.

A demo needs bills that actually produce findings. These are synthetic, built from the real
published prices in data/a3_reference_table.csv so the price comparison has something true
to compare against, with problems planted deliberately - and every file says SYNTHETIC on
its face so none can be mistaken for a real statement.

    python3 tools/make_sample_bills.py
"""
import csv, pathlib, random, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "samples" / "bills"
HOSPITAL = "Doylestown Hospital"


def posted():
    table = {}
    with open(ROOT / "data" / "a3_reference_table.csv", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["hospital_name"].strip().lower() == HOSPITAL.lower():
                table[r["code"].strip()] = (float(r["hospital_gross_charge"]),
                                            r["description"].strip())
    return table


P = posted()


def at(code, mult=1.0, units=1):
    """A line at a multiple of the hospital's own published price."""
    price, desc = P[code]
    return (code, desc[:30], units, round(price * mult * units, 2))


BILLS = [
    ("01_overcharged", "Lines billed above the hospital's own published price.",
     lambda: [at("70450", 1.9), at("72148", 1.56), at("71046", 1.0), at("80048", 1.0)]),
    ("02_duplicate", "The same code posted twice on one statement.",
     lambda: [at("99284"), at("99284"), at("70450"), at("36415", 1.0, 2)]),
    ("03_quantity", "A visit-level code billed ten times over.",
     lambda: [at("99282", 1.0, 10), at("80048"), at("71046")]),
    ("04_unspecified", "An unclassified drug code that declines to say what was given.",
     lambda: [at("70450"), ("J3490", "UNCLASSIFIED DRUG", 1, 4200.00),
              ("A9270", "NON-COVERED ITEM", 1, 860.00)]),
    ("05_ambulance", "Includes a ground ambulance line - the federal carve-out.",
     lambda: [("A0427", "ALS AMBULANCE EMERGENCY", 1, 1890.00), at("99285", 1.4),
              at("70450")]),
    ("06_summary_not_itemised", "A summary with no billing codes - should be rejected.",
     lambda: [("", "HOSPITAL SERVICES", 1, 8420.00), ("", "PHARMACY", 1, 1180.00)]),
    ("07_clean", "Every line exactly at the published price - nothing should flag.",
     lambda: [at("70450"), at("71046"), at("80048"), at("76700")]),
]


def as_text(note, lines):
    total = sum(l[3] for l in lines)
    out = [HOSPITAL.upper(),
           "Patient Financial Services    Account 88211904",
           "*** SYNTHETIC SAMPLE - NOT A REAL STATEMENT ***",
           f"({note})", "",
           f"{'CODE':<8}{'DESCRIPTION':<34}{'QTY':>4}{'AMOUNT':>13}"]
    for code, desc, units, amt in lines:
        out.append(f"{code:<8}{desc:<34}{units:>4}{amt:>13,.2f}")
    out += ["", f"{'TOTAL DUE':>46}{total:>13,.2f}"]
    return "\n".join(out)


def as_image(lines, path):
    from PIL import Image, ImageDraw, ImageFont

    def font(sz, bold=False):
        for p in ("/System/Library/Fonts/Supplemental/Courier New Bold.ttf" if bold
                  else "/System/Library/Fonts/Supplemental/Courier New.ttf",
                  "/System/Library/Fonts/Supplemental/Arial.ttf"):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
        return ImageFont.load_default()

    W, H = 1400, 1000
    im = Image.new("RGB", (W, H), (250, 249, 246))
    d = ImageDraw.Draw(im)
    y = 60
    d.text((70, y), HOSPITAL.upper(), font=font(30, True), fill=(20, 20, 20)); y += 44
    d.text((70, y), "Patient Financial Services    Account 88211904",
           font=font(20), fill=(90, 90, 90)); y += 32
    d.text((70, y), "SYNTHETIC SAMPLE - NOT A REAL STATEMENT",
           font=font(18, True), fill=(165, 60, 60)); y += 40
    d.line([(70, y), (W - 70, y)], fill=(140, 140, 140), width=2); y += 32
    d.text((70, y), f"{'CODE':<9}{'DESCRIPTION':<34}{'QTY':>5}{'AMOUNT':>16}",
           font=font(21), fill=(40, 40, 40)); y += 34
    for code, desc, units, amt in lines:
        d.text((70, y), f"{code or '--':<9}{desc:<34}{units:>5}{amt:>16,.2f}",
               font=font(21), fill=(25, 25, 25)); y += 34
    y += 12
    d.line([(70, y), (W - 70, y)], fill=(60, 60, 60), width=2); y += 28
    total = sum(l[3] for l in lines)
    d.text((760, y), f"{'TOTAL DUE':<12}{total:>16,.2f}", font=font(23, True),
           fill=(20, 20, 20))
    im = im.rotate(-0.5, expand=False, fillcolor=(250, 249, 246))
    px = im.load()
    for _ in range(70000):
        x, yy = random.randrange(W), random.randrange(H)
        r, g, b = px[x, yy]; n = random.randint(-11, 11)
        px[x, yy] = (max(0, min(255, r + n)), max(0, min(255, g + n)),
                     max(0, min(255, b + n)))
    im.save(path, quality=85)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    built = []
    for name, note, make in BILLS:
        lines = make()
        (OUT / f"{name}.txt").write_text(as_text(note, lines))
        try:
            as_image(lines, OUT / f"{name}.jpg")
            extra = "txt + jpg"
        except Exception as e:
            extra = f"txt only ({type(e).__name__})"
        built.append((name, note, sum(l[3] for l in lines), extra))

    (OUT / "README.md").write_text(
        "# Sample bills\n\nSynthetic statements built from the real published prices in\n"
        "`data/a3_reference_table.csv`, with problems planted deliberately so each check has\n"
        "something to find. Every file is marked SYNTHETIC on its face.\n\n"
        "All are for **Doylestown Hospital** - pick that in the Bill tab, or the price\n"
        "comparison has nothing to compare against.\n\n"
        "| File | What it is for | Total |\n|---|---|---|\n"
        + "\n".join(f"| `{n}` | {note} | ${t:,.2f} |" for n, note, t, _ in built)
        + "\n\nRebuild with `python3 tools/make_sample_bills.py`.\n")

    print(f"built {len(built)} sample bill(s) in samples/bills/\n")
    for n, note, t, extra in built:
        print(f"  {n:<26} ${t:>10,.2f}  {extra}")
        print(f"  {'':<26} {note}")


if __name__ == "__main__":
    sys.exit(main())
