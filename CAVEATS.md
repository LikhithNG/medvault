# Caveats

Read this before relying on anything MedVault tells you.

## Executive summary

**The nine things that limit this tool**, in the order they are most likely to matter:
it gives information and not advice (1); "no record found" is a question, not a finding
(2); an unanswered rights question is unknown, never "no" (3); the rights checks cover
four federal protections and no state law (4); a model reads documents and can misread
them (5); a verified NPI confirms the number, never the person typing it (6); a clinician
account can read every patient's records and there is no grant mechanism yet (7); the
question box sends your records to a model and does not check drug interactions (8); and
none of this is a medical record (9).

**The one added since the Assignment 2 PRD.** That PRD said the MVP "processes in memory,
persists nothing, and never sends a name, MRN or date of birth to a model — only the code
and the amount." MedVault is a vault: it persists everything, by design. And a vision
model has to see the whole page to read a bill, so the name on it goes too. Section 5 and
section 8 say what actually happens. The PRD's sentence was never achievable for an image
and is not true of this build.

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

**The whole page goes to the model, your name included.** There is no redaction step, and
there cannot usefully be one on the image path: a vision model has to see the page to read
what is on it, and the name, the account number and the date of birth are printed on the
same page as the codes. The PRD this project grew out of promised to send "only the code
and the amount". That is achievable for a text PDF and not for a photograph, and this
build does not do it for either. What it does instead: the page is sent once, for
extraction, and is not retained by the model provider.

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

**Two things leave the machine, and only when you ask for them:** a document you upload to
be read (section 5), and a question you type on the Ask screen, which goes with the text of
your records (section 8). Every check, price comparison and finding is computed locally.

## 8. What the question box is, and is not

The Ask screen answers questions about the records in your own vault. A model writes those
answers, which means they carry every limitation a model has, and the interface is built
around that rather than around hiding it.

**What is not generated.** The findings above the box — a duplicate medicine, a course
whose end date has passed, a medicine that collides with a recorded allergy — are
arithmetic over your records. No model is involved and nothing leaves the server to
produce them.

**What never reaches a model.** A question that reads like an emergency is answered with a
phone number and nothing else. A question asking whether to start, stop, skip or change a
dose is answered by naming the prescriber and quoting what your own record says; that
relabelling is applied after the answer comes back, so it does not depend on the model
having been honest about what it was doing.

**What the badges mean.** *From your records* means the answer cites at least one record,
and the records it cites are named under it. *General information* means it is textbook
knowledge about a drug or a test and is **not a statement about you**. *Your records do not
say* means the answer is not in the vault. An answer that claimed the records but cited
none is relabelled before it is shown.

**It does not check drug interactions.** There is no interaction database here. A check
that quietly does not run is worse than one that is absent, so it is absent and the screen
says so.

**The allergy check is a prompt, not a clearance.** It matches the medicine's name, and a
short hand-written table of five drug families, against what you typed in the allergies
box — that is what catches "allergic to penicillin" against amoxicillin, which share no
letters. Five families is not a formulary. It will miss things. Tell the hospital your
allergies yourself.

**Your question and your records are sent to the model to answer it.** That is the one
place in this app where record text leaves the server other than a document being read.

## 9. This is not a medical record

MedVault holds a copy of paperwork you chose to upload. It is not a clinical system, it is
not interoperable with any hospital, nothing in it is authoritative, and no clinician is
obliged to accept it. Do not rely on it in an emergency as the only source of anything.
