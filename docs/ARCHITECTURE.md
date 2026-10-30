# How MedVault fits together

Six diagrams: the whole system, the two journeys a patient takes through it (a bill and a
record), the fence around the one bot that writes its own words, the workflow that collects
the reference data, and what the vault stores. GitHub draws them from the Mermaid source
below; every box names the file that does the work.

**The one rule under all of it: AI reads, math decides.** Only two agents call a model, the
Reader and the Companion. Every number a patient acts on, every warning and every letter is
computed in plain Python from a published file.

## 1. The system

```mermaid
flowchart TB
    people(["Patient on a phone or laptop · clinician with a checked NPI"])

    subgraph app["The app · app.py"]
        screens["Card · Add · Records · Medicines · Bill · Ask<br/>Review and Records for clinicians"]
    end

    subgraph ai["AI reads"]
        reader["Reader<br/>extract.py"]
        companion["Companion<br/>ask.py"]
    end

    subgraph math["Math decides"]
        checker["Checker<br/>checker.py"]
        advocate["Advocate<br/>dispute.py"]
        scheduler["Scheduler<br/>schedule.py"]
        liaison["Liaison<br/>liaison.py"]
    end

    guards["Around every agent: safety filter · receipts rule · records cross-check<br/>bill checks · rights check · daily AI limits"]

    subgraph stored["Stored"]
        vault[("The vault · db.py<br/>SQLite on a laptop, Turso when hosted")]
        prices[("Published prices · 9 hospitals<br/>data/a3_reference_table.csv")]
    end

    subgraph outside["Outside services"]
        models["Gemini and Groq<br/>read documents, answer questions"]
        medicare["Medicare fee schedule<br/>medicare.py"]
        registry["National provider registry<br/>npi.py"]
    end

    n8n["n8n workflow · workflow/"]

    people --> app
    app --> ai & math
    ai --> models
    ai & math --- guards
    math --> prices & medicare
    app --> vault
    app -. "clinician sign-up" .-> registry
    n8n -. "collects reference data" .-> prices
```

## 2. Checking a bill

The journey behind slides 3 and 9 of the pitch: a photo or PDF in, a letter out, and a
question at every line the patient's own records cannot back.

```mermaid
flowchart TD
    start(["A photo or PDF of a bill, or its lines pasted in"])
    read["Reader reads every line<br/>PDF text: Groq · photo: Gemini · pasted: no AI"]
    total{"Lines add up to<br/>the printed total?"}
    again["Read again on the other provider;<br/>still off, it is shown with a warning"]
    codes{"Billing codes on it?"}
    stop(["Stop: ask the hospital<br/>for the itemised bill"])

    subgraph checks["Every line, checked four ways · pipeline.py"]
        direction LR
        price["Hospital's own published price<br/>and Medicare's rate<br/>checker.py · medicare.py"]
        face["The bill's own face<br/>duplicates, unspecified codes, credits<br/>billchecks.py"]
        law["What the law may give you<br/>rights.py"]
        records["Did it happen?<br/>the patient's records<br/>crosscheck.py"]
    end

    letter["Advocate writes the letter: each disputed line<br/>with the hospital's figure, file and date<br/>dispute.py · receipts.py"]
    screen(["On screen: every finding, the letter,<br/>and answers about the bill · explain.py"])

    start --> read --> total
    total -- yes --> codes
    total -- no --> again --> codes
    codes -- no --> stop
    codes -- yes --> checks
    checks -- "anything flagged" --> letter --> screen
    checks -- "nothing flagged" --> screen
```

## 3. Filing a record, and what comes of it

```mermaid
flowchart TD
    doc(["Photo or PDF of a prescription,<br/>lab report or discharge note"])
    limit{"AI reads left today?<br/>quota.py"}
    none(["Not read: try tomorrow,<br/>nothing stored"])
    read["Reader: type, date, doctor, summary,<br/>every medicine, every lab result<br/>extract.py · Gemini"]
    check["The patient checks and corrects it,<br/>results included, before filing"]
    filed[("Filed: the record, its medicines,<br/>its results, and the original page")]
    card["Emergency card<br/>current medicines, allergies"]
    sched["Scheduler: today's doses<br/>and a calendar file for the phone<br/>schedule.py"]
    liai["Liaison: what's still open<br/>overdue follow-up, allergy clash,<br/>duplicate, finished course<br/>liaison.py"]
    team(["The doctors the patient chose<br/>see the same list · careteam.py"])
    comp["Companion answers questions<br/>from these records · ask.py"]

    doc --> limit
    limit -- no --> none
    limit -- yes --> read --> check --> filed
    filed --> card & sched & liai & comp
    liai --> team
```

## 4. The fence around the Companion

The one agent that writes its own sentences. An emergency and a dose decision never get the
model's words, and every answer has to say where it came from.

```mermaid
flowchart TD
    q(["A patient's question"])

    subgraph before["Before the model sees it · safety.py"]
        emergency{"Reads like<br/>an emergency?"}
        dose{"Asks for a<br/>dose decision?"}
    end

    model["The model answers from the patient's own records<br/>ask.context_pack · Gemini"]

    subgraph after["After it writes"]
        label{"Labelled an emergency<br/>or a prescriber question?"}
        tidy["An answer that claims the records but cites none<br/>becomes general knowledge; dose advice is replaced"]
    end

    nine(["Fixed answer: call 911"])
    presc(["Fixed answer: ask your prescriber,<br/>named, with what the record says"])
    shown(["Shown with the records it used"])
    down(["Model unavailable: the reply leads with 911"])

    q --> emergency
    emergency -- yes --> nine
    emergency -- no --> dose
    dose -- yes --> presc
    dose -- no --> model
    model -- "no answer" --> down
    model --> label
    label -- emergency --> nine
    label -- prescriber --> presc
    label -- neither --> tidy --> shown
```

Measured in `tools/safety_eval.py` on held-out questions written without access to this code:
103 of 103 emergencies get the 911 answer and 126 of 127 dose questions the prescriber answer,
with the patterns first and the model's label second.

## 5. Where the reference data comes from

`workflow/Nagaralu_Gurumurthy_Likhith_MedVault_Workflow.json` is an n8n workflow of nine
nodes. `workflow/run_without_n8n.mjs` runs the same code outside n8n, against the same
endpoints, so it can be checked before it is imported.

```mermaid
flowchart TD
    run(["When you click Run"]) --> scope["Scope: nine hospitals, 31 codes"]
    scope --> cms["CMS enforcement actions<br/>data.cms.gov"]
    scope --> pfs["Medicare fee schedule<br/>data.cms.gov"]
    scope --> hpt["Each hospital's cms-hpt.txt<br/>where its price file lives"]
    cms & pfs & hpt --> join["Clean and join · To CSV"]
    join --> save[("medvault_reference_DATE.csv")]
    save -. "checked, with the price rows<br/>read from each hospital's file" .-> table[("data/a3_reference_table.csv<br/>262 rows · 9 hospitals · 31 codes")]
```

## 6. What the vault stores

```mermaid
erDiagram
    accounts ||--o{ records : "owns"
    accounts ||--o{ profile : "card fields"
    accounts ||--o{ care_team : "patient chooses"
    care_team ||--o| care_views : "sign-ins noted"
    records ||--o{ medications : "medicines read off it"
    records ||--o{ lab_results : "results read off it"
    accounts ||--o{ ai_use : "AI reads per day"

    accounts {
        int id PK
        text email
        text role "patient or clinician"
        text npi "clinicians, registry-checked"
    }
    records {
        int id PK
        int owner_id FK
        text kind
        text service_date
        text provider
        text title
        text summary
        blob file_bytes "the original page"
        text provenance "self-filed, verified, clinical"
    }
    medications {
        int id PK
        int record_id FK
        text name
        text dose
        text frequency
        text duration
        int active
    }
    lab_results {
        int id PK
        int record_id FK
        text name
        text value
        text unit
        text reference_range
        text flag "only if printed"
    }
    care_team {
        int patient_id PK
        int clinician_id PK
        real added_at
    }
    care_views {
        int patient_id PK
        int clinician_id PK
        real last_seen_at
        int visits
    }
    profile {
        int account_id PK
        text key PK
        text value
    }
    ai_use {
        int account_id PK
        text day PK
        int n
    }
```

`agent_runs` sits beside these: how long each agent took and whether it worked, and nothing
about whose run it was or what it read.

## Where each part lives

| Part | Files |
|---|---|
| Screens | `app.py`, `medvault/screen_*.py`, `medvault/ui.py`, `medvault/agentsui.py` |
| The six agents, as data | `medvault/agents.py` (Madison role, job, what it never does, time budget) |
| Reading documents | `medvault/extract.py`, `medvault/gemini.py`, `medvault/groq.py`, `medvault/pool_state.py` |
| Pricing a bill | `medvault/checker.py`, `medvault/medicare.py`, `medvault/billchecks.py`, `medvault/pipeline.py` |
| The letter and its sources | `medvault/dispute.py`, `medvault/receipts.py`, `medvault/explain.py` |
| Records, rights, safety | `medvault/crosscheck.py`, `medvault/rights.py`, `medvault/safety.py`, `medvault/ask.py` |
| Reminders and what's open | `medvault/schedule.py`, `medvault/liaison.py`, `medvault/careteam.py` |
| Accounts and storage | `medvault/accounts.py`, `medvault/npi.py`, `medvault/db.py`, `medvault/store.py`, `medvault/quota.py` |
| Reference data | `data/`, `workflow/` |
| Measurements | `tools/accuracy_test.py`, `tools/reader_eval.py`, `tools/safety_eval.py`, `tools/companion_eval.py`, `outputs/` |
| Tests | `tests/` (536) |
