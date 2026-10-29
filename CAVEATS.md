# Caveats

Read this before relying on anything MedVault tells you.

## Executive summary

**The nine things that limit this tool**, in the order they are most likely to matter:
it gives information and not advice (1); "no record found" is a question, not a finding
(2); an unanswered rights question is unknown, never "no" (3); the rights checks cover
four federal protections and no state law (4); a model reads documents and can misread
them (5); a verified NPI confirms the number, never the person typing it (6); a clinician sees only
the patients who put them on their care team, but there is no log of who looked (7); the
question box sends your records to a model and does not check drug interactions (8); two
hospitals' enforcement counts are failed joins recorded as zeros (9); hosted, the storage
is temporary and the way out is a file you download (10); and none of this is a medical
record (11).

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
extraction. Whether the provider keeps it is set by the provider's terms, and on the free
Gemini tier this demo runs on, Google may use it to improve its products and its reviewers
may read it (README, "Where your data lives"). So: sample paperwork only, and a paid tier
before anything real.

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

**A clinician sees only the patients who chose them.** A patient adds a clinician to their
care team from the Card screen, by the email on that clinician's MedVault account, and
only an account whose NPI was checked against the national registry can be added. Removing
someone takes effect on their next screen.

This used to be the largest hole in the project. Until 28 October every verified clinician
could read every patient's records - the review queue and the Records tab both listed the
whole server - while the Card screen was about to tell patients "nobody else can". The
care team closes it for every clinician screen, not only the new one, and
`tests/test_liaison.py` holds that an empty team means *no* records rather than all of
them.

What the care team does not do: confirm that the person signed in as a clinician is that
clinician (see section 6), or log who looked at what. There is no audit trail of access.

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

## 9. Two zeros in the enforcement data that are not zeros

The reference table records, per hospital, how many price-transparency enforcement actions
CMS has taken against it. Those counts were verified against the full live CMS file on
26 October 2026 — all 13,355 actions, not the first page — and **all nine hospitals agree
exactly**. `tools/verify_enforcement.py` is that check, and it can be re-run.

The same check found something the build did not: **two of the nine are recorded as 0, and
both are failed joins rather than clean records.**

| The table says | CMS lists it as | Actual actions |
|---|---|---|
| `BAYLOR SCOTT & WHITE ALL SAINTS MEDICAL CENTER - FORT WORTH` → 0 | `BAYLOR SCOTT & WHITE ALL SAINTS MEDICAL CENTER` | **2** |
| `Community Hospital of Stokes` → 0 | `LIFEBRITE COMMUNITY HOSPITAL OF STOKES` | **5** |

A city suffix and an operator prefix each broke a name-and-state match, and the miss was
written down as a count. The data is left as it was collected rather than hand-patched —
it is a submitted artifact — but the app no longer reads those zeros as findings: a
hospital whose match method is `none` is reported as *not matched*, in those words, and
never as a hospital with nothing against it.

This is the same distinction as section 2. "Not found" is not "did not happen", and a tool
that blurs the two on a medical record has no business making the claim on a hospital.

## 10. Hosted, the storage is temporary

Deployed to a free tier, the database lives on a disk that does not survive a restart —
and the host restarts an app when it has been idle and on every redeploy. Everything in
the vault goes with it.

That is a broken promise for something called a vault, so the app says so on the screen
where your records are, and both halves of the way out exist: **Download my vault** writes
everything except the original scans to a JSON file, and **Restore it** puts that file
back. Restoring the same file twice adds nothing the second time.

A clinician's confirmation does not travel with the file. The account that gave it does
not exist on the machine the file lands on, so the badge would be a claim with nothing
behind it — every restored record is labelled as filed by you.

**This is fixable, and the fix is in the repository.** Setting `TURSO_DATABASE_URL` and
`TURSO_AUTH_TOKEN` moves the vault off that disk and into a libSQL database that outlives
a restart; the app then says so on the same screen instead of warning. Without those two
secrets it is still a file, and still temporary — the warning is about the storage, not
about being hosted, so it tells you which of the two you actually have.

## 11. This is not a medical record

MedVault holds a copy of paperwork you chose to upload. It is not a clinical system, it is
not interoperable with any hospital, nothing in it is authoritative, and no clinician is
obliged to accept it. Do not rely on it in an emergency as the only source of anything.
