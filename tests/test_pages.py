#!/usr/bin/env python3
"""Which page of a statement each charge is printed on.

A long itemised statement runs to several pages, and a billing office asked about
"72148, MRI lumbar" has to go looking for it. A line read off a PDF now carries the page
it is printed on, found by plain text matching on that page's own text layer - nothing a
model said - and the letter names the page. A photo is one page and says nothing.
"""
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))

import checker    # noqa: E402
import dispute    # noqa: E402
import extract    # noqa: E402
import paste      # noqa: E402
import pipeline   # noqa: E402
import rights     # noqa: E402

PAGE_1 = "STATEMENT p1\n2026-03-14 70450 CT HEAD/BRAIN W/O CONTRAST 1 3,076.10"
PAGE_2 = "STATEMENT p2\n2026-03-14 72148 MRI LUMBAR WITHOUT 1 9,374.04\nTOTAL 12,450.14"


def _pdf(*pages):
    """A real PDF with one line of text per page line, built by hand: no PDF library here
    can write one, and a fixture file would hide what is on each page."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None,
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        lines = text.split("\n")
        body = "BT /F1 11 Tf 14 TL 50 750 Td " + " ".join(
            f"({line}) Tj T*" for line in lines) + " ET"
        objects.append(f"<< /Length {len(body)} >>\nstream\n{body}\nendstream")
        content = len(objects)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                       f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content} 0 R >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for n, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{obj}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n"
            f"%%EOF\n").encode()
    return out


def test_a_pdf_gives_back_each_pages_own_text():
    pages = extract.pdf_pages(io.BytesIO(_pdf(PAGE_1, PAGE_2)))
    assert len(pages) == 2
    assert "70450" in pages[0] and "72148" not in pages[0]
    assert "72148" in pages[1]


def test_each_line_is_given_the_page_it_is_printed_on():
    lines = paste.lines("2026-03-14 70450 CT HEAD 1 3,076.10\n"
                        "2026-03-14 72148 MRI LUMBAR 1 9,374.04")
    paged = extract.with_pages(lines, [PAGE_1, PAGE_2])
    assert [l["page"] for l in paged] == [1, 2]
    assert "page" not in lines[0], "the lines read are not changed in place"


def test_a_one_page_statement_says_nothing_about_pages():
    lines = paste.lines("2026-03-14 70450 CT HEAD 1 3,076.10")
    assert extract.with_pages(lines, [PAGE_1]) == lines
    assert extract.with_pages(lines, None) == lines


def test_the_same_charge_on_two_pages_is_given_both_in_order():
    """A repeated line is read twice; each copy is the next page it appears on."""
    same = "2026-03-14 72148 MRI LUMBAR WITHOUT 1 9,374.04"
    lines = paste.lines(same + "\n" + same)
    paged = extract.with_pages(lines, ["header", same, same])
    assert [l["page"] for l in paged] == [2, 3]


def test_a_line_found_on_no_page_is_given_no_page_rather_than_a_guess():
    lines = paste.lines("2026-03-14 99284 ER VISIT 1 2,150.00")
    paged = extract.with_pages(lines, [PAGE_1, PAGE_2])
    assert paged[0].get("page") is None


def test_a_code_inside_a_longer_number_is_not_a_match():
    lines = paste.lines("2026-03-14 7045 SHORT CODE 1 12.00")
    paged = extract.with_pages(lines, ["ref 704501 12.00", "nothing here"])
    assert paged[0].get("page") is None


def test_the_letter_names_the_page_of_each_disputed_line():
    lines = extract.with_pages(
        paste.lines("2026-03-14 70450 CT HEAD/BRAIN W/O CONTRAST 1 3,076.10\n"
                    "2026-03-14 72148 MRI LUMBAR WITHOUT 1 9,374.04"),
        [PAGE_1, PAGE_2])
    ctx = rights.context(coverage=rights.UNKNOWN, emergency=None, nonprofit_hospital=None,
                         in_network_facility=None, gfe_amount=None)
    out = pipeline.check_lines(lines, hospital="Doylestown Hospital", ctx=ctx, records=[],
                               patient_name="Test Patient",
                               price_table=checker.load_reference())
    pages = {l["code"]: l.get("page") for l in out["priced"]["lines"]}
    assert pages == {"70450": 1, "72148": 2}
    assert "72148 — MRI LUMBAR WITHOUT\n" in out["letter"]
    assert "On page 2 of the statement." in out["letter"]


def test_a_letter_from_a_photo_mentions_no_page():
    text = dispute.letter({"hospital_name": "A Hospital", "billed_total": 420.0,
                           "posted_total": 0.0, "questionable_amount": 0.0,
                           "lines": [{"code": "J3490", "description": "DRUG", "units": 1,
                                      "charged": 420.0, "verdict": "NOT_POSTED"}]})
    assert "page" not in text.lower()


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  pass · {name}"); n += 1
    print(f"{n} passed")
