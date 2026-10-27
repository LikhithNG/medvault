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

## Is this the right amount?

Two comparisons, because neither alone is enough.

**What this hospital publishes.** Every hospital must post its standard charges under
45 CFR 180. The 262 rows in `data/a3_reference_table.csv` are nine of those files, collected
by hand. This is the stronger comparison where it applies — a hospital charging more than
the price it published itself is a question with a document behind it.

**What Medicare allows.** The table covers nine hospitals, and that was the weakest thing
about this project: a bill from anywhere else got the rights checks, the arithmetic and the
records cross-check, and silence under "is this the right amount". `medicare.py` fills that
with a national benchmark covering **any CPT code**, which also carries the thing a bill
never does — a plain-English name:

| The bill says | The benchmark says | Billed | Medicare allows |
|---|---|---|---|
| `72148 MRI LUMBAR WITHOUT` | MRI of the Lower Back without Contrast | $9,374.04 | $191.72 · **49×** |
| `70450 CT HEAD/BRAIN W/O CONTRAST` | CT Scan of the Head without Contrast | $3,076.10 | $106.55 · **29×** |
| `80048 LAB BASIC METABOLIC PANEL` | Basic Metabolic Panel (BMP) | $241.00 | $8.46 · **29×** |

Two things stated in the interface, not just here. **A Medicare rate is not a price cap** —
a hospital may charge a commercial patient more and usually does, so a multiple is context
for a conversation and not evidence of an overcharge. And the endpoint is a third party
republishing the CMS Physician Fee Schedule rather than CMS itself; the figures carry CMS's
own dataset name and effective year, which is checkable, but a republisher can be wrong in a
way data.cms.gov cannot.

Coverage is CPT. HCPCS Level II — J-codes for drugs, G- and A-codes — is outside the
dataset, and the screen says which codes it could not benchmark rather than leaving them out
silently. Lookups are cached to disk, so a demo does not depend on a network and nobody
re-reads the same code off a free service.

This also settles **Change 9** from the Itemized user testing, where a tester asked for
`HCHG CT ABD & PELVIS W/CON` to be translated and the answer was no, because a plain-English
description was the one thing on the card that would have been invented. It is sourced now.

## Who can say a record is real

The obvious answer is "only let doctors upload". It is the wrong one: it empties the vault
on day one and leaves the product waiting for an adoption it cannot get, because no
clinician joins an app with no patients in it.

So nobody is locked out. Every record carries **where it came from**, and the badge is drawn
on all of them — including the unverified ones, because a vault that only labels the good
records teaches people that a missing badge means nothing.

| Badge | What it means |
|---|---|
| **Self-filed** | The patient uploaded it. Useful to them. Evidence to nobody. |
| **Clinician-verified** | A clinician with a registry-checked NPI confirmed it matches what they issued. |
| **Filed by a clinician** | Uploaded directly by a verified clinician. |

A clinician account requires an **NPI checked live against the CMS national provider
registry** — a free public API that returns the provider's licence number, state, specialty
and status. An invented number is rejected.

What that proves, stated precisely because the feature rests on it: the NPI exists, is
active, and matches a licence. It does **not** prove the person typing it is that provider.
Closing that gap needs an out-of-band step — an email to the address on file, hospital SSO —
which is beyond a student project. The interface therefore says *"NPI verified"* and never
*"identity verified"*.

Verification is attributed and reversible. Each verified record stores which account
confirmed it and when, so a badge can always be traced back to a checked NPI, and a
clinician who confirmed the wrong record can withdraw it — which demotes the record to
self-filed rather than deleting it.

## What the law may already give you

Checking prices is the smaller half. A rate difference of a few hundred dollars is real; a
right you did not know you had can be worth the whole bill — and none of it needs a price
file, only a few questions about your situation.

| If | Then |
|---|---|
| You are uninsured or self-pay | You were owed a written **Good Faith Estimate** before scheduled care. Billed $400+ above it, you can use federal dispute resolution instead of negotiating alone. |
| The hospital is non-profit | It **must** have a financial assistance policy and cap what it charges people who qualify — and is not required to tell you that you do. |
| It was emergency care | Balance billing above in-network cost sharing is generally **prohibited**, not negotiable. |
| The facility was in network | An out-of-network anaesthetist or radiologist at it generally cannot balance-bill you either. |
| The bill includes a ground ambulance | Federally **un**protected — a deliberate carve-out. ~22 states fill the gap; this tool does not know which and will not guess. |

Anything you leave as *"Not sure"* is treated as unknown and the check is skipped, and the
screen says which questions went unanswered. Filling those gaps with plausible negatives
would make a tidier result and would eventually tell someone they have no protection that
they in fact have.

Three more checks need nothing but the bill: **lines that do not multiply out**
(units × price ≠ charge), **unspecified codes** like `J3490` that decline to say what was
provided, and exact duplicates.

This idea — and the discipline around it — is owed to
[DAVANO Innovation Lab's `itemize`](https://github.com/DAVANO-INNOVATION-LAB/itemize),
whose README makes the point plainly: a patient's rights are usually worth more than any
coding error.

> **Read [CAVEATS.md](CAVEATS.md) before relying on anything this says.** It is
> information, not advice; "no record found" does not mean a service did not happen; and
> an unanswered question is never a no.

## Screens

| | |
|---|---|
| **Landing** | What a signed-out visitor sees: what the product does, how it works, the caveats, and the sign-in panel beside it rather than instead of it. |
| **Card** | The emergency screen. Name, blood type, allergies in red, conditions, current medicines, who to call. |
| **Add** | Photograph or upload a document. It is read once, you check what was read, then it is filed. |
| **Records** | Everything in one timeline, searchable, filterable, with the original attached. |
| **Medicines** | Pulled out of prescriptions automatically, with dose, frequency and what it is for. |
| **Check a bill** | A hospital bill against your own records. |
| **Ask** | What your records already show, checked by arithmetic — then a bot you can ask about your medicines and treatment. |
| **Review** | Clinicians only. The queue of patient-filed records waiting to be confirmed. |

Navigation is a fixed bar at the bottom of the screen with an icon above each label — where
a thumb already is on a phone, and the clearest signal that this is an app rather than a web
page. Which icons are drawn is inferred in CSS from how many tabs the signed-in role
produced, six for a patient and two for a clinician, because Streamlit strips `<script>`
from markdown so a class set from Python never arrives.

## Where the AI is, and where it deliberately is not

Two jobs need a model: reading a photograph, and answering a question about what a
document means. Nothing else here does.

| Step | How |
|---|---|
| Turn a **PDF** into line items | **Groq — open-source models** (gpt-oss, Qwen), free tier |
| Turn a **photograph** into line items | Vision model, one call — see below |
| Duplicate codes | `checker.py` — pure Python |
| Charged above the published price | `checker.py` — pure Python |
| Quantity billed many times over | `checker.py` — pure Python |
| Lines that do not multiply out | `billchecks.py` — pure Python |
| Unspecified codes | `billchecks.py` — pure Python |
| What the law may give you | `rights.py` — pure Python |
| Whether your records support a line | `crosscheck.py` — pure Python |
| The dispute letter | `dispute.py` — a template over the Checker's figures |
| Answering questions about the bill | `explain.py` — reads the findings, generates nothing |
| Duplicate medicines, finished courses, allergy collisions | `ask.py` — pure Python |
| Answering questions about your records | `ask.py` — a model, inside the fence below |

### Open models where they work

A PDF from a patient portal has a text layer, so reading it needs no vision at all — those
go to **Groq's free tier, running open-source models**, and come back in about a second.
A photograph does need vision, and Groq's key reaches no vision model, so that path still
uses Gemini. The interface says which one answered.

Two things that cost a measurement to find. Groq's JSON mode refuses a prompt that does not
contain the word "json", while Gemini copies a worked JSON example straight into its answer
when one is present — so the requirement is added per provider rather than compromising the
shared prompt. And Groq's JSON mode does not enforce a schema, only valid JSON, so the model
named the rows `"charges"` instead of `"line_items"` and every line was silently dropped;
the parser now accepts the obvious synonyms, because losing a whole bill to a key name is a
worse failure than a slightly loose parser.

**The explainer is not a chatbot, and that is the design.** Asked "why is this charge
wrong?", a language model produces a fluent paragraph whether or not it knows — and on a
medical bill a fluent wrong paragraph is what sends somebody into a billing office quoting
a figure that collapses under one question. Everything `explain.py` says is read out of
findings the deterministic checks produced. It can be wrong only if the Checker was wrong,
it can never invent a figure, and when it does not understand a question it says so and
lists what it can answer. Ten tests exist to keep it that way, including one that scans
every answer for a dollar amount the checks never established.

### Two bots, and only one of them generates

The bill explainer is not a chatbot and the records bot is, and those are the same decision
rather than two different ones. A bill's findings are a bounded set of computed facts, so
generating a sentence about them adds a way to be wrong and nothing else. "What did this
discharge summary actually say" has no lookup table behind it, and a patient holding a
document they cannot read is exactly who a careful reader helps most.

So `ask.py` calls a model, with a fence around it:

- **The checks run first, and never call one.** Duplicate medicines, a course whose end
  date has passed, a medicine that collides with a recorded allergy — those are arithmetic
  over the vault, and the answers must not vary with a model's mood, so they do not.
- **Two questions never reach it.** Anything that reads like an emergency is answered with a
  phone number. Anything asking for a dose decision is answered by naming the prescriber and
  then quoting what the record actually says. Both are pattern-matched in Python, and the
  dose relabelling is applied *after* the model answers, so the badge does not depend on the
  model having classified itself honestly.
- **Every answer says where it came from.** *From your records* must cite at least one
  record, and an answer claiming the records while citing none is relabelled *general* before
  it is shown. A citation of a record belonging to someone else is dropped.
- **It does not check drug interactions**, and says so, because there is no interaction
  database here and a check that quietly does not run is worse than one that is absent.

The allergy check knows a short, hand-written table of drug families, because "allergic to
penicillin" and "amoxicillin" share no letters and a name-only check would call that pair
unrelated. The table is five families long and the interface says so on every card it
produces. It is a prompt to ask a question, not a clearance.

## Where your data lives

In one SQLite file next to the app (`vault.db`, git-ignored). Uploaded originals are stored
in it too, so the vault can hand back the actual page rather than only what a model made of
it — a summary is useful, the original is evidence.

Two things leave that machine, both only when you ask for them. A document you upload is
sent once to a model to be read, and is not retained there. A question you type into the Ask
screen is sent with the text of your records, because an answer about your records cannot be
given without them. Everything else — every check, every price comparison, every finding —
is computed locally.

**This is a student project, not a medical device.** It holds a copy of your paperwork; it
does not interpret results, and it is not a substitute for talking to your doctor.

## The mark

The logo is a shield with the cross cut *out* of it rather than drawn on top. That is the
only version that survives being nineteen pixels wide in a navigation rail: a cross drawn
in a second colour turns to mush at that size, a hole does not.

`medvault/logo.py` holds the geometry as the list of segments the shield is made of. The
SVG path string is generated from that list, the CSS mask is generated from the same string,
and `tools/make_icons.py` samples the same curves with Pillow to draw the home-screen PNGs —
so the mark in the app bar and the icon on a phone cannot drift apart by somebody forgetting
to re-export. There is no SVG rasteriser in this project's dependencies and adding one for
four files would be silly.

Three things here fail silently rather than loudly, so they are covered by tests
(`tests/test_logo.py`): geometry drifting outside its 48-unit box, which clips the icon; a
`#` from a colour reaching a CSS data URI unescaped, which truncates the rest of the rule;
and two copies of the mark on one page sharing a mask id, where the second wins and the
first renders as a solid square.

## One product, two shapes

**On a phone** it installs. Open the URL, *Add to Home Screen*, and it launches from an
icon with no browser chrome — a manifest and the Apple meta tags make it a standalone app
rather than a bookmark. Navigation is a bar across the bottom, where a thumb already is.

**On a laptop** the bar becomes a left rail with the brand at the top of it, and the
content moves over beside it, widening to 1000px. Same code, same login, same data.

Records stay one column on a wide screen. A two-up grid was written and then taken out
again: each card is its own `st.markdown` call, so there is no single element for a grid to
live on, and a rule that can never match is worse than no rule — it reads as a feature.

Getting those tags into the page needed a workaround worth knowing about: Streamlit
sanitises `<link>` and `<meta>` out of `st.markdown`, and `set_page_config` only reaches the
favicon. `medvault/pwa.py` injects them from a zero-height `components.v1.html` block, which
renders in an iframe and can reach `window.parent.document.head`.

One trap caught by checking rather than assuming: every relative URL inside a manifest
resolves against **the manifest's own location**, not the page's. Served from
`/app/static/`, the icon paths became `/app/static/app/static/icon-192.png` — three 404s —
and `start_url` would have launched the installed app at `/app/static/` instead of the app.

## Trying it without a bill of your own

`samples/bills/` has seven synthetic statements, as text and as photographs, built from the
real published prices in `data/a3_reference_table.csv` so the comparison has something true
to compare against. Each one is planted to trip a specific check, and every file says
SYNTHETIC on its face.

All are for **Doylestown Hospital** — pick that in the Bill tab or the price comparison has
nothing to work with.

| File | Trips |
|---|---|
| `01_overcharged` | Two lines above the published price · $4,822 questionable |
| `02_duplicate` | The same code posted twice |
| `03_quantity` | A visit code billed ten times over |
| `04_unspecified` | `J3490` and `A9270` — codes that decline to say what was given |
| `05_ambulance` | The federal ground-ambulance carve-out |
| `06_summary_not_itemised` | Nothing — it is rejected, which is the point |
| `07_clean` | Nothing. A bill where everything matches has to look like one. |

Rebuild them with `python3 tools/make_sample_bills.py`.

## Running it

```bash
pip install -r requirements.txt
python3 -m streamlit run app.py
```

Reads `GEMINI_API_KEY` from a local `.env` (git-ignored) or from Streamlit secrets when
deployed. Without a key everything works except reading new documents.

```bash
python3 tests/test_db.py          # storage keeps what it is given
python3 tests/test_crosscheck.py  # the cross-check never accuses
python3 tests/test_accounts.py    # a badge cannot exist without a checked NPI
```

## Built on

The reader (`medvault/gemini.py`, `medvault/pool_state.py`) is carried over from
[Itemized](https://github.com/LikhithNG/itemized-app), where it took four separate defects
on a live server to make reliable: a key that never reached the server, a validator that
rejected a valid key, a pool that spent three minutes on unreachable models, and model
retirement that never expired. All four fixes are in the copy here.

Likhith Nagaralu Gurumurthy · INFO 7375 Branding and AI · Northeastern University
