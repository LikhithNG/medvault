#!/usr/bin/env python3
"""Everything the screen looks like, in one place.

Designed phone-first and then allowed to breathe on a laptop, rather than the other way
round. The test this has to pass is not "does it look nice" - it is "can someone hold this
up at a hospital desk and have the person behind it read it", which turns out to rule out
most of what a dashboard normally does: small type, dense tables, colour-only meaning.
"""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root{
  --ink:#10151C; --soft:#5B6673; --faint:#8B95A3;
  --line:#E3E8EF; --bg:#F7F9FC; --card:#FFFFFF;
  --accent:#0F6FDE; --accent-soft:#EAF2FE;
  --warn:#B45309; --warn-soft:#FEF6E7;
  --danger:#B42318; --danger-soft:#FEF0EF;
  --ok:#067647; --ok-soft:#ECFDF3;
  --sans:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}

.stApp{background:var(--bg)}
html,body,[class*="css"]{font-family:var(--sans)}
.block-container{padding:1rem .9rem 4rem!important;max-width:620px}
#MainMenu,footer,header{visibility:hidden}

h1,h2,h3,h4{font-family:var(--sans);color:var(--ink);letter-spacing:-.02em}

/* ---- the bar at the top -------------------------------------------------- */
.brand{display:flex;align-items:center;gap:.6rem;margin:0 0 1.1rem}
.brand .mark{width:34px;height:34px;border-radius:10px;background:var(--accent);
  display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;
  font-size:17px;flex:0 0 auto}
.brand .name{font-weight:800;font-size:19px;color:var(--ink);letter-spacing:-.03em}
.brand .tag{font-size:12.5px;color:var(--faint);margin-left:auto;text-align:right;
  line-height:1.3}

/* ---- the emergency card -------------------------------------------------- */
.idcard{background:linear-gradient(145deg,#0F6FDE,#0B57AE);color:#fff;border-radius:18px;
  padding:1.15rem 1.2rem;margin-bottom:.9rem;box-shadow:0 6px 22px rgba(15,111,222,.22)}
.idcard .who{font-size:23px;font-weight:800;letter-spacing:-.03em;line-height:1.15}
.idcard .sub{font-size:13px;opacity:.86;margin-top:.15rem}
.idcard .grid{display:flex;gap:.55rem;margin-top:.95rem;flex-wrap:wrap}
.idcard .cell{background:rgba(255,255,255,.14);border-radius:11px;padding:.5rem .7rem;
  flex:1 1 30%;min-width:88px}
.idcard .cell .k{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;opacity:.8}
.idcard .cell .v{font-size:16px;font-weight:700;margin-top:.1rem;word-break:break-word}

/* a red band, because an allergy is the one thing that must not be missed */
.alert{background:var(--danger-soft);border:1px solid #F6C9C4;border-left:4px solid var(--danger);
  border-radius:12px;padding:.7rem .85rem;margin-bottom:.8rem}
.alert .k{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;
  color:var(--danger)}
.alert .v{font-size:15.5px;font-weight:600;color:#7A1710;margin-top:.15rem;line-height:1.35}

/* ---- a record in the timeline -------------------------------------------- */
.rec{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:.8rem .9rem;margin-bottom:.6rem}
.rec .top{display:flex;align-items:center;gap:.5rem;margin-bottom:.3rem}
.rec .pill{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
  padding:.2rem .5rem;border-radius:999px;background:var(--accent-soft);color:var(--accent)}
.rec .when{font-size:12px;color:var(--faint);margin-left:auto;white-space:nowrap}
.rec .title{font-size:16.5px;font-weight:700;color:var(--ink);line-height:1.3}
.rec .who{font-size:13px;color:var(--soft);margin-top:.1rem}
.rec .sum{font-size:13.5px;color:var(--soft);margin-top:.4rem;line-height:1.45}
.rec .nofile{font-size:12px;color:var(--faint);margin-top:.4rem}

/* ---- where a record came from -------------------------------------------- */
/* The badge is the product's whole answer to "how do I know this is real". It is drawn on
   every record, including the unverified ones, because a vault that only labels the good
   records teaches people that an absent badge means nothing. */
.prov{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
  padding:.2rem .5rem;border-radius:999px;display:inline-flex;align-items:center;gap:.25rem}
.prov.self{background:#F1F3F7;color:#5B6673;border:1px solid #DFE4EC}
.prov.verified{background:var(--ok-soft);color:var(--ok);border:1px solid #BCE5CF}
.prov.clinical{background:var(--accent-soft);color:var(--accent);border:1px solid #CFE3FB}
.provwhy{font-size:12px;color:var(--faint);margin-top:.35rem;line-height:1.45}

/* The signed-in strip. Named .whoami, not .who: .who was already the provider line inside
   a record card, and reusing it wrapped every hospital name in a box that looked like an
   editable text field. */
.whoami{display:flex;align-items:center;gap:.5rem;background:var(--card);
  border:1px solid var(--line);border-radius:12px;padding:.55rem .7rem;margin-bottom:.7rem}
.whoami .av{width:30px;height:30px;border-radius:9px;background:var(--accent-soft);
  color:var(--accent);display:flex;align-items:center;justify-content:center;
  font-weight:800;font-size:13px;flex:0 0 auto}
.whoami .nm{font-size:14px;font-weight:700;color:var(--ink);line-height:1.2}
.whoami .rl{font-size:11.5px;color:var(--faint)}
.whoami .chk{margin-left:auto;font-size:10.5px;font-weight:700;text-transform:uppercase;
  letter-spacing:.05em;color:var(--ok);background:var(--ok-soft);border:1px solid #BCE5CF;
  padding:.2rem .5rem;border-radius:999px;text-align:right;line-height:1.3}

/* ---- a medicine ---------------------------------------------------------- */
.med{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:.8rem .9rem;margin-bottom:.55rem;border-left:4px solid var(--accent)}
.med .n{font-size:16px;font-weight:700;color:var(--ink);line-height:1.3}
.med .d{font-size:13.5px;color:var(--soft);margin-top:.25rem;line-height:1.45}
.med .why{font-size:12.5px;color:var(--faint);margin-top:.3rem;font-style:italic}

/* ---- the bill cross-check ------------------------------------------------ */
.hit{border-radius:14px;padding:.85rem .9rem;margin-bottom:.6rem;border:1px solid}
.hit.bad{background:var(--danger-soft);border-color:#F6C9C4;border-left:4px solid var(--danger)}
.hit.warn{background:var(--warn-soft);border-color:#F7E0B5;border-left:4px solid var(--warn)}
.hit.ok{background:var(--ok-soft);border-color:#C4E9D5;border-left:4px solid var(--ok)}
.hit .h{font-size:14.5px;font-weight:700;margin-bottom:.2rem}
.hit.bad .h{color:#7A1710} .hit.warn .h{color:#7A4A06} .hit.ok .h{color:#05502F}
.hit .b{font-size:13.5px;color:#333B45;line-height:1.5}
.hit .amt{float:right;font-weight:800;font-size:16px}

/* ---- small shared bits --------------------------------------------------- */
.sect{font-size:11.5px;font-weight:700;text-transform:uppercase;letter-spacing:.09em;
  color:var(--soft);margin:1.3rem 0 .55rem}
.empty{background:var(--card);border:1px dashed var(--line);border-radius:14px;
  padding:1.6rem 1rem;text-align:center;color:var(--faint);font-size:14px;line-height:1.5}
.note{font-size:12.5px;color:var(--faint);line-height:1.5;margin-top:.5rem}

.stButton>button{border-radius:11px;font-weight:600;font-family:var(--sans);
  border:1px solid var(--line);padding:.55rem 1rem}
.stButton>button[kind="primary"]{background:var(--accent);border-color:var(--accent)}
div[data-testid="stFileUploader"]{background:var(--card);border-radius:14px;
  border:1px solid var(--line);padding:.5rem}
/* Streamlit's default tabs are low-contrast and accented red, which on a health app
   reads as an alert. Made legible, and moved onto the product's own blue. */
div[data-baseweb="tab-list"]{gap:.1rem;background:var(--card);padding:.25rem;
  border-radius:12px;border:1px solid var(--line);margin-bottom:.4rem}
div[data-baseweb="tab-list"] button{flex:1 1 auto;border-radius:9px;padding:.45rem .2rem!important}
div[data-baseweb="tab-list"] button p{font-family:var(--sans)!important;font-size:12.5px!important;
  font-weight:600!important;color:var(--soft)!important;margin:0}
div[data-baseweb="tab-list"] button[aria-selected="true"]{background:var(--accent-soft)}
div[data-baseweb="tab-list"] button[aria-selected="true"] p{color:var(--accent)!important}
div[data-baseweb="tab-highlight"],div[data-baseweb="tab-border"]{display:none}

/* The stock info box is also red-tinted here; make it match the rest. */
div[data-testid="stAlert"]{border-radius:12px;font-size:13.5px;background:var(--accent-soft);
  border:1px solid #CFE3FB}
div[data-testid="stAlert"] *{color:#0B4F9E!important}

/* Inputs. Streamlit inherits the viewer's dark-mode preference, which turned the paste box
   black with black text on a page that is otherwise light. Pinned explicitly. */
textarea,input[type="text"],div[data-baseweb="textarea"],div[data-baseweb="input"],
div[data-baseweb="select"]>div{background:var(--card)!important;color:var(--ink)!important;
  border-radius:11px!important;border-color:var(--line)!important;
  font-family:var(--sans)!important;font-size:14.5px!important}
textarea::placeholder,input::placeholder{color:var(--faint)!important}

/* Captions carry most of the plain-language explanation in this app; they have to be read,
   not merely present. */
div[data-testid="stCaptionContainer"],div[data-testid="stCaptionContainer"] p{
  color:var(--soft)!important;font-size:13px!important;line-height:1.5!important}
label p{color:var(--soft)!important;font-size:13px!important;font-weight:600!important}
</style>
"""


def brand(tag=""):
    return (f"<div class='brand'><div class='mark'>M</div>"
            f"<div class='name'>MedVault</div>"
            f"<div class='tag'>{tag}</div></div>")


def section(label):
    return f"<div class='sect'>{label}</div>"


def empty(message):
    return f"<div class='empty'>{message}</div>"


PROV_CLASS = {"SELF": "self", "VERIFIED": "verified", "CLINICAL": "clinical"}


def provenance_badge(record):
    """The badge for one record. Always drawn, including for unverified records."""
    import accounts
    prov = record.get("provenance") or "SELF"
    label = accounts.PROVENANCE.get(prov, accounts.PROVENANCE["SELF"])[0]
    return f"<span class='prov {PROV_CLASS.get(prov, 'self')}'>{label}</span>"


def signed_in_strip(account):
    import accounts
    initials = "".join(w[0] for w in (account.get("display_name") or
                                      account.get("email", "?")).split()[:2]).upper()
    role = ("Clinician" if account["role"] == "clinician" else "Patient")
    chk = ""
    if accounts.is_verified_clinician(account):
        chk = (f"<div class='chk'>NPI {account['npi']} verified<br>"
               f"{account.get('npi_specialty') or ''}</div>")
    return (f"<div class='whoami'><div class='av'>{initials or '?'}</div>"
            f"<div><div class='nm'>{account.get('display_name') or account['email']}</div>"
            f"<div class='rl'>{role}</div></div>{chk}</div>")
