#!/usr/bin/env python3
"""Plain words for the clinical ones, so a search finds what a person means.

A Mere Medical user (github.com/cfu288/mere-medical, MIT) typed "diabetes" and "high blood
sugar" into its search bar, found nothing, and reported search as broken; Mere answered
with AI embeddings sent to OpenAI. This is the local answer: a short list of the plain
words people use, each with the clinical words their records use instead. Nothing leaves
the vault, and nothing here decides anything - it only widens a search.

Each extra term is at least three letters, because a search runs as LIKE '%term%' and a
two-letter term ("ct") matches every doctor and every practice in the vault.
"""
LAY_TERMS = {
    "high blood sugar": ("diabetes", "glucose", "a1c", "hyperglycemia"),
    "blood sugar": ("glucose", "diabetes", "a1c"),
    "sugar": ("glucose", "diabetes", "a1c"),
    "high blood pressure": ("hypertension", "blood pressure"),
    "blood pressure": ("hypertension", "systolic", "diastolic"),
    "heart attack": ("myocardial infarction", "troponin"),
    "stroke": ("cerebrovascular", "cerebral infarction"),
    "water pill": ("diuretic", "furosemide", "hydrochlorothiazide"),
    "blood thinner": ("anticoagulant", "warfarin", "apixaban", "rivaroxaban", "heparin"),
    "cholesterol": ("lipid", "ldl", "hdl", "statin", "atorvastatin"),
    "kidney": ("renal", "creatinine", "egfr"),
    "liver": ("hepatic", "bilirubin", "alanine", "aspartate"),
    "thyroid": ("tsh", "thyroxine", "levothyroxine"),
    "anemia": ("hemoglobin", "haemoglobin", "ferritin", "iron"),
    "low iron": ("ferritin", "iron", "hemoglobin"),
    "blood count": ("cbc", "hemoglobin", "white blood cell", "platelet"),
    "urine test": ("urinalysis", "urine"),
    "flu shot": ("influenza",),
    "flu jab": ("influenza",),
    "tetanus": ("tdap", "tetanus"),
    "covid": ("sars-cov-2", "covid-19", "coronavirus"),
    "broken bone": ("fracture",),
    "heartburn": ("gerd", "reflux", "omeprazole"),
    "painkiller": ("analgesic", "ibuprofen", "acetaminophen", "paracetamol"),
    "inhaler": ("albuterol", "salbutamol", "fluticasone", "puff"),
    "antibiotic": ("amoxicillin", "azithromycin", "cephalexin", "doxycycline", "penicillin"),
    "x-ray": ("radiograph", "xray"),
    "scan": ("mri", "ultrasound", "imaging", "tomography"),
}
MAX_TERMS = 12


def expand(query):
    """The query, then the clinical words for any plain phrase inside it. Order kept, no repeats."""
    text = (query or "").strip()
    terms = [text]
    lowered = text.casefold()
    for phrase, clinical in LAY_TERMS.items():
        if phrase in lowered:
            terms += [t for t in clinical if t not in terms]
    return terms[:MAX_TERMS]
