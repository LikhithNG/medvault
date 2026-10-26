# MedVault

Every piece of your medical paperwork, on the phone in your pocket.

You photograph a prescription or a discharge summary once. MedVault reads it, files it, and
pulls the medicines out of it. At a hospital desk you open one screen instead of carrying a
folder — blood type, allergies, conditions, what you are currently taking, and the original
document itself if anyone asks for it.

## Why it exists

The paperwork a patient accumulates is the only complete record of their own care, and it
lives in a drawer. Hospitals hold fragments: each one knows what it did, none knows what the
others did, and the patient is the only person in the room who was present for all of it —
carrying a plastic bag of paper to prove it.

## The part that is not a filing cabinet

A record vault can answer a question a price comparison cannot.

Checking a hospital bill against published prices asks *was this the right amount for a CT
scan*. Checking it against your own records asks **did I have a CT scan at all** — and that
is the question a patient can actually act on.

> **Nothing in your vault from this date.** Ask what this charge was for. You have filed
> nothing from 02 Jun 2026 — your closest record is 80 days away. That may simply be
> paperwork you never received.

That last sentence is load-bearing. A vault holds what its owner remembered to upload, which
is never everything, so "no record found" means *you have nothing on file supporting this* —
never *this did not happen*. Every verdict is phrased as a question to ask the billing
office. There are tests in `tests/test_crosscheck.py` whose only job is to keep it that way.

## Screens

| | |
|---|---|
| **Card** | The emergency screen. Name, blood type, allergies in red, conditions, current medicines, who to call. |
| **Add** | Photograph or upload a document. It is read once, you check what was read, then it is filed. |
| **Records** | Everything in one timeline, searchable, filterable, with the original attached. |
| **Medicines** | Pulled out of prescriptions automatically, with dose, frequency and what it is for. |
| **Check a bill** | A hospital bill against your own records. |

## Where your data lives

In one SQLite file next to the app (`vault.db`, git-ignored). Uploaded originals are stored
in it too, so the vault can hand back the actual page rather than only what a model made of
it — a summary is useful, the original is evidence.

When a document is read, the page is sent once to a vision model for extraction and is not
retained there. Nothing else leaves the machine the app runs on.

**This is a student project, not a medical device.** It holds a copy of your paperwork; it
does not interpret results, and it is not a substitute for talking to your doctor.

## Running it

```bash
pip install -r requirements.txt
python3 -m streamlit run app.py
```

Reads `GEMINI_API_KEY` from a local `.env` (git-ignored) or from Streamlit secrets when
deployed. Without a key everything works except reading new documents.

```bash
python3 tests/test_db.py
python3 tests/test_crosscheck.py
```

## Built on

The reader (`medvault/gemini.py`, `medvault/pool_state.py`) is carried over from
[Itemized](https://github.com/LikhithNG/itemized-app), where it took four separate defects
on a live server to make reliable: a key that never reached the server, a validator that
rejected a valid key, a pool that spent three minutes on unreachable models, and model
retirement that never expired. All four fixes are in the copy here.

Likhith Nagaralu Gurumurthy · INFO 7375 Branding and AI · Northeastern University
