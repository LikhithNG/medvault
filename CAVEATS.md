# Caveats

Read this before relying on anything MedVault tells you.

This document is deliberately specific. A tool that tells people what to ask about a
medical bill — or what their records do and do not show — can cause real harm by being
confidently wrong, so every known limit is written down here rather than left to be
discovered by whoever hits it first.

The idea of keeping this file, and several of the checks it describes, are owed to
[DAVANO Innovation Lab's `itemize`](https://github.com/DAVANO-INNOVATION-LAB/itemize).

---

## 1. This is information, not advice

MedVault produces information. It is not legal, medical, financial or insurance advice,
and using it creates no professional relationship of any kind. It cannot tell you what you
owe, what you are entitled to, or whether a charge is wrong.

Nothing here has been reviewed by an attorney, a certified medical coder, or a patient
advocate. It is a student project. Verify anything you intend to act on — every finding
names its source so that you can.

## 2. "No record found" is not "it did not happen"

The bill cross-check compares a bill against the records **you have uploaded**, which is
never everything. Paperwork gets lost, is never issued, or arrives months later.

So a line with no matching record means *you have nothing on file that supports this*. It
does not mean the service was not provided, and the tool will not say that it does. Every
such finding is phrased as a question for the billing office. `tests/test_crosscheck.py`
exists to keep it that way.

## 3. An unanswered question is not a "no"

The rights checks depend on things only you know: whether you were insured, whether it was
an emergency, whether the hospital is non-profit. **Anything you leave as "Not sure" is
treated as unknown and the relevant check is skipped** — the screen then tells you which
questions were not answered.

Filling those gaps with plausible negatives would make a tidier result and would
eventually tell somebody they have no protection that they in fact have.

## 4. What the rights checks do not cover

- **State law is not implemented at all.** State protections vary enormously and are often
  the more valuable half. MedVault checks federal rules only.
- **Self-funded employer plans** — roughly two-thirds of workers with employer coverage —
  are generally outside state insurance law. MedVault does not ask which you have.
- **Ground ambulance** is named as a federal carve-out, and deliberately stops there.
- Dollar thresholds and citations are current to the rules as written at the time of
  building. Check the regulation if you are going to rely on it.

## 5. What the reader of a document is and is not

Uploaded documents are read by a vision model. It can misread a dose, a date or a decimal
point, and it is asked to return null rather than guess — but it does not always comply.

**Check what was read before you file it.** The confirmation screen exists for that, and
the original document is stored alongside the extracted text so the page itself is always
recoverable. A summary is useful; the original is evidence.

The reader does not interpret results. "Haemoglobin 11.2 g/dL" is recorded as printed;
whether that is low is for your doctor.

## 6. What "clinician-verified" means, and does not

A clinician account requires an NPI checked live against the CMS national provider
registry. That confirms **the number is real, active, and matches a licence**.

It does **not** confirm that the person typing it is that provider. Closing that gap needs
an out-of-band step — an email to the address on file, or hospital SSO — which is beyond
this project. The interface therefore says *"NPI verified"*, never *"identity verified"*.

A verified badge means a registry-checked account confirmed the record. It is not an audit
of the underlying care.

## 7. Where your data lives, and who can see it

Records are stored in a SQLite file on whatever machine runs the app. Profiles and records
are scoped per account — a defect where every account shared one health card was found and
fixed, and `tests/test_isolation.py` holds that line.

**A clinician account can currently read every patient's records.** This is what makes the
review queue work, and there is no mechanism yet for a patient to grant or revoke that
access. If you deploy this for more than one real person, that is the first thing to fix.

Deployed to a hosted service, the database lives on that server, not on your phone. It is
not encrypted at rest.

## 8. This is not a medical record

MedVault holds a copy of paperwork you chose to upload. It is not a clinical system, it is
not interoperable with any hospital, nothing in it is authoritative, and no clinician is
obliged to accept it. Do not rely on it in an emergency as the only source of anything.
