#!/usr/bin/env python3
"""What a medical record is, in one place.

Every other module reads these definitions rather than inventing its own, so a record kind
added here appears in the uploader, the timeline and the cross-check without three separate
edits. This is the lesson from Itemized, where the definition of a billing code lived in four
places and they disagreed.
"""

# The kinds of paper a patient actually accumulates. Ordered by how often they are needed at
# a hospital desk, because that is the order the timeline filters are drawn in.
KINDS = {
    "prescription":  ("Prescription",      "Medicines prescribed to you"),
    "lab":           ("Lab report",        "Blood work, urine, pathology"),
    "imaging":       ("Scan or imaging",   "X-ray, CT, MRI, ultrasound"),
    "visit":         ("Visit summary",     "Discharge notes, consultation notes"),
    "vaccination":   ("Vaccination",       "Immunisation records"),
    "insurance":     ("Insurance",         "Cards, policy documents, approvals"),
    "bill":          ("Bill",              "An itemised hospital statement"),
    "other":         ("Other",             "Anything else worth keeping"),
}

KIND_ORDER = list(KINDS)


def kind_label(kind):
    return KINDS.get(kind, KINDS["other"])[0]


def kind_hint(kind):
    return KINDS.get(kind, KINDS["other"])[1]


# What the reader is asked to pull out of an uploaded document. Kept deliberately small:
# every field here has to be worth a patient's trust, and a field the model guesses at is
# worse than a field left empty.
RECORD_FIELDS = {
    "kind":          "One of: " + ", ".join(KIND_ORDER),
    "service_date":  "The date on the document, as YYYY-MM-DD. Null if not printed.",
    "provider":      "The hospital, clinic or doctor named on it. Null if not printed.",
    "title":         "A short plain description, e.g. 'Chest X-ray' or 'Amoxicillin course'.",
    "summary":       "One or two sentences a patient would understand. No jargon.",
}

# A prescription carries more, and it is the part people most need to recall at a desk.
MED_FIELDS = {
    "name":      "Medicine name as printed.",
    "dose":      "Strength and amount, e.g. '500 mg, 1 tablet'. Null if not printed.",
    "frequency": "How often, e.g. 'twice a day'. Null if not printed.",
    "duration":  "How long, e.g. '7 days'. Null if not printed.",
    "reason":    "What it is for, if the document says. Null otherwise.",
}

# The emergency card: the screen you hold up at a hospital desk when you cannot talk.
PROFILE_FIELDS = (
    "full_name", "date_of_birth", "blood_type", "allergies",
    "conditions", "emergency_name", "emergency_phone", "notes",
)
