#!/usr/bin/env python3
"""Check a clinician against the national provider registry.

CMS publishes every licensed US provider's NPI record at npiregistry.cms.hhs.gov - free, no
key, no account. That makes this the one credential in the product that is checked against
something real rather than asserted by whoever typed it.

What this does and does not prove, stated plainly because the whole feature rests on it:
it proves the NPI exists, is active, and belongs to the name and licence shown. It does not
prove the person typing it is that provider. Closing that gap needs an out-of-band step -
an email to the address on file, a hospital SSO - which is beyond a student project. The
interface therefore says "NPI verified", never "identity verified", and the difference is
not cosmetic.
"""
import json, re, urllib.parse, urllib.request

API = "https://npiregistry.cms.hhs.gov/api/"
TIMEOUT = 15


def _name(basic):
    """Individual providers carry first/last; organisations carry a single name."""
    parts = [basic.get("first_name"), basic.get("last_name")]
    person = " ".join(p.title() for p in parts if p)
    return person or (basic.get("organization_name") or basic.get("name") or "").title()


def lookup(npi):
    """Look up one NPI. Returns (record_or_None, problem_or_None).

    Never raises: a registry that is down must leave a clinician unverified, not break the
    page they are standing in front of.
    """
    npi = re.sub(r"\D", "", str(npi or ""))
    if len(npi) != 10:
        return None, "An NPI is exactly 10 digits."

    url = API + "?" + urllib.parse.urlencode({"version": "2.1", "number": npi})
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            data = json.loads(r.read())
    except Exception as e:
        return None, f"The provider registry could not be reached ({type(e).__name__})."

    if data.get("Errors"):
        return None, str(data["Errors"][0].get("description", "Registry rejected the number."))
    results = data.get("results") or []
    if not results:
        return None, f"No provider is registered under NPI {npi}."

    r0 = results[0]
    basic = r0.get("basic", {}) or {}
    tax = next((t for t in (r0.get("taxonomies") or []) if t.get("primary")),
               (r0.get("taxonomies") or [{}])[0])
    addr = next((a for a in (r0.get("addresses") or []) if a.get("address_purpose") == "LOCATION"),
                (r0.get("addresses") or [{}])[0])

    if (basic.get("status") or "").upper() != "A":
        return None, f"NPI {npi} is in the registry but is not active."

    return {
        "npi":        r0.get("number"),
        "name":       _name(basic),
        "credential": (basic.get("credential") or "").strip(" ,."),
        "is_person":  r0.get("enumeration_type") == "NPI-1",
        "specialty":  tax.get("desc"),
        "license":    tax.get("license"),
        "license_state": tax.get("state"),
        "city":       (addr.get("city") or "").title(),
        "state":      addr.get("state"),
    }, None

