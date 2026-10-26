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
.idcard{background:linear-gradient(150deg,#1A7BEA 0%,#0F6FDE 45%,#0A4E9E 100%);color:#fff;
  border-radius:18px;padding:1.2rem 1.2rem 1.25rem;margin-bottom:.9rem;position:relative;
  overflow:hidden;box-shadow:0 8px 26px rgba(15,111,222,.26)}
/* a soft highlight across the top so the card has a surface rather than a flat fill */
.idcard::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(120% 70% at 85% -10%,rgba(255,255,255,.22),transparent 60%)}
.idcard>*{position:relative;z-index:1}
.idcard .who{font-size:23px;font-weight:800;letter-spacing:-.03em;line-height:1.15}
.idcard .sub{font-size:13px;opacity:.86;margin-top:.15rem}
.idcard .grid{display:flex;gap:.5rem;margin-top:.95rem}
.idcard .cell{background:rgba(255,255,255,.15);border-radius:11px;padding:.5rem .6rem;
  flex:1 1 0;min-width:0}
.idcard .cell .k{font-size:10px;text-transform:uppercase;letter-spacing:.07em;opacity:.82}
/* A date of birth is ten characters and was wrapping onto two lines inside its cell, which
   made the card look broken. The cells share the width evenly and clip rather than wrap. */
.idcard .cell .v{font-size:15px;font-weight:700;margin-top:.12rem;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}

/* a red band, because an allergy is the one thing that must not be missed */
.alert{background:var(--danger-soft);border:1px solid #F6C9C4;border-left:4px solid var(--danger);
  border-radius:12px;padding:.7rem .85rem;margin-bottom:.8rem}
.alert .k{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;
  color:var(--danger)}
.alert .v{font-size:15.5px;font-weight:600;color:#7A1710;margin-top:.15rem;line-height:1.35}

/* ---- a record in the timeline -------------------------------------------- */
.rec{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:.8rem .9rem;margin-bottom:.6rem;box-shadow:0 1px 2px rgba(16,21,28,.04);
  transition:box-shadow .15s ease,transform .15s ease}
.rec:active{transform:scale(.995);box-shadow:0 1px 1px rgba(16,21,28,.06)}
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
  padding:.8rem .9rem;margin-bottom:.55rem;border-left:4px solid var(--accent);
  box-shadow:0 1px 2px rgba(16,21,28,.04)}
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
/* ---- the navigation bar -------------------------------------------------- */
/* Streamlit draws tabs as a strip at the top of the page, which reads as a web page.
   Fixed to the bottom with an icon above each label, it reads as an app - and on a phone
   it also puts the controls where a thumb already is. The icons are masks rather than
   background images so they take their colour from the active state. */
div[data-baseweb="tab-list"]{
  position:fixed;left:0;right:0;bottom:0;z-index:999;
  display:flex;gap:0;padding:.35rem .25rem calc(.35rem + env(safe-area-inset-bottom));
  background:rgba(255,255,255,.92);backdrop-filter:saturate(180%) blur(14px);
  -webkit-backdrop-filter:saturate(180%) blur(14px);
  border-top:1px solid var(--line);border-radius:0;margin:0;
  box-shadow:0 -2px 18px rgba(16,21,28,.06)}
div[data-baseweb="tab-list"] button{
  flex:1 1 0;min-width:0;border-radius:10px;background:transparent!important;
  padding:.3rem .1rem .25rem!important;display:flex;flex-direction:column;
  align-items:center;gap:.18rem}
div[data-baseweb="tab-list"] button p{
  font-family:var(--sans)!important;font-size:10.5px!important;font-weight:600!important;
  color:var(--faint)!important;margin:0;letter-spacing:-.01em;white-space:nowrap}
div[data-baseweb="tab-list"] button[aria-selected="true"] p{color:var(--accent)!important}
div[data-baseweb="tab-highlight"],div[data-baseweb="tab-border"]{display:none}

/* one icon per position, drawn above the label */
div[data-baseweb="tab-list"] button::before{
  content:"";width:21px;height:21px;display:block;background:var(--faint);
  -webkit-mask-size:contain;mask-size:contain;-webkit-mask-repeat:no-repeat;
  mask-repeat:no-repeat;-webkit-mask-position:center;mask-position:center}
div[data-baseweb="tab-list"] button[aria-selected="true"]::before{background:var(--accent)}

/* the panel has to clear the bar, or the last record sits underneath it */
div[data-baseweb="tab-panel"]{padding-bottom:4.6rem}

/* There is exactly one tab group in this app and it is the navigation. The sign-in screen
   uses a radio precisely so that stays true - a second group would be pinned to the bottom
   of the screen wearing navigation icons. */

/* The stock info box is red-tinted by default; make it match the rest. */
div[data-testid="stAlert"]{border-radius:12px;font-size:13.5px;background:var(--accent-soft);
  border:1px solid #CFE3FB}
div[data-testid="stAlert"] *{color:#0B4F9E!important}

/* Inputs. Streamlit inherits the viewer's dark-mode preference, which turned the paste box
   black with black text on a page that is otherwise light. Pinned explicitly. */
textarea,input[type="text"],input[type="password"],div[data-baseweb="textarea"],
div[data-baseweb="input"],div[data-baseweb="select"]>div{
  background:var(--card)!important;color:var(--ink)!important;border-radius:11px!important;
  border-color:var(--line)!important;font-family:var(--sans)!important;
  font-size:14.5px!important}
textarea::placeholder,input::placeholder{color:var(--faint)!important}

/* Captions carry most of the plain-language explanation in this app; they have to be read,
   not merely present. */
div[data-testid="stCaptionContainer"],div[data-testid="stCaptionContainer"] p{
  color:var(--soft)!important;font-size:13px!important;line-height:1.5!important}
label p{color:var(--soft)!important;font-size:13px!important;font-weight:600!important}



/* the icons. Which set appears is inferred from the number of tabs the role drew. */
div[data-baseweb="tab-list"]:has(button:nth-child(5)) button:nth-child(1)::before{-webkit-mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Crect%20x%3D%222.5%22%20y%3D%224.5%22%20width%3D%2219%22%20height%3D%2215%22%20rx%3D%223%22%2F%3E%3Cpath%20d%3D%22M12%2015.2s-3.1-2-3.1-4a1.8%201.8%200%200%201%203.1-1.2%201.8%201.8%200%200%201%203.1%201.2c0%202-3.1%204-3.1%204Z%22%2F%3E%3C%2Fsvg%3E");mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Crect%20x%3D%222.5%22%20y%3D%224.5%22%20width%3D%2219%22%20height%3D%2215%22%20rx%3D%223%22%2F%3E%3Cpath%20d%3D%22M12%2015.2s-3.1-2-3.1-4a1.8%201.8%200%200%201%203.1-1.2%201.8%201.8%200%200%201%203.1%201.2c0%202-3.1%204-3.1%204Z%22%2F%3E%3C%2Fsvg%3E")}
div[data-baseweb="tab-list"]:has(button:nth-child(5)) button:nth-child(2)::before{-webkit-mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M3%208.5h3l1.6-2.2h8.8L18%208.5h3v10H3z%22%2F%3E%3Ccircle%20cx%3D%2212%22%20cy%3D%2213%22%20r%3D%223.4%22%2F%3E%3C%2Fsvg%3E");mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M3%208.5h3l1.6-2.2h8.8L18%208.5h3v10H3z%22%2F%3E%3Ccircle%20cx%3D%2212%22%20cy%3D%2213%22%20r%3D%223.4%22%2F%3E%3C%2Fsvg%3E")}
div[data-baseweb="tab-list"]:has(button:nth-child(5)) button:nth-child(3)::before{-webkit-mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M7%203.5h7l4%204V17a2%202%200%200%201-2%202H7a2%202%200%200%201-2-2V5.5a2%202%200%200%201%202-2Z%22%2F%3E%3Cpath%20d%3D%22M14%203.5V8h4%22%2F%3E%3Cpath%20d%3D%22M8.5%2012.5h7M8.5%2015.5h4.5%22%2F%3E%3C%2Fsvg%3E");mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M7%203.5h7l4%204V17a2%202%200%200%201-2%202H7a2%202%200%200%201-2-2V5.5a2%202%200%200%201%202-2Z%22%2F%3E%3Cpath%20d%3D%22M14%203.5V8h4%22%2F%3E%3Cpath%20d%3D%22M8.5%2012.5h7M8.5%2015.5h4.5%22%2F%3E%3C%2Fsvg%3E")}
div[data-baseweb="tab-list"]:has(button:nth-child(5)) button:nth-child(4)::before{-webkit-mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Crect%20x%3D%223.2%22%20y%3D%228.6%22%20width%3D%2217.6%22%20height%3D%226.8%22%20rx%3D%223.4%22%20transform%3D%22rotate%28-40%2012%2012%29%22%2F%3E%3Cpath%20d%3D%22M9.6%209.6l4.8%204.8%22%2F%3E%3C%2Fsvg%3E");mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Crect%20x%3D%223.2%22%20y%3D%228.6%22%20width%3D%2217.6%22%20height%3D%226.8%22%20rx%3D%223.4%22%20transform%3D%22rotate%28-40%2012%2012%29%22%2F%3E%3Cpath%20d%3D%22M9.6%209.6l4.8%204.8%22%2F%3E%3C%2Fsvg%3E")}
div[data-baseweb="tab-list"]:has(button:nth-child(5)) button:nth-child(5)::before{-webkit-mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M6%203.5h12v17l-2-1.4-2%201.4-2-1.4-2%201.4-2-1.4-2%201.4z%22%2F%3E%3Cpath%20d%3D%22M9%208h6M9%2011.5h6M9%2015h3.5%22%2F%3E%3C%2Fsvg%3E");mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M6%203.5h12v17l-2-1.4-2%201.4-2-1.4-2%201.4-2-1.4-2%201.4z%22%2F%3E%3Cpath%20d%3D%22M9%208h6M9%2011.5h6M9%2015h3.5%22%2F%3E%3C%2Fsvg%3E")}
div[data-baseweb="tab-list"]:not(:has(button:nth-child(3))) button:nth-child(1)::before{-webkit-mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M7%203.5h10a2%202%200%200%201%202%202V18a2%202%200%200%201-2%202H7a2%202%200%200%201-2-2V5.5a2%202%200%200%201%202-2Z%22%2F%3E%3Cpath%20d%3D%22M8.8%2012.2l2.2%202.2%204.2-4.6%22%2F%3E%3C%2Fsvg%3E");mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M7%203.5h10a2%202%200%200%201%202%202V18a2%202%200%200%201-2%202H7a2%202%200%200%201-2-2V5.5a2%202%200%200%201%202-2Z%22%2F%3E%3Cpath%20d%3D%22M8.8%2012.2l2.2%202.2%204.2-4.6%22%2F%3E%3C%2Fsvg%3E")}
div[data-baseweb="tab-list"]:not(:has(button:nth-child(3))) button:nth-child(2)::before{-webkit-mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M7%203.5h7l4%204V17a2%202%200%200%201-2%202H7a2%202%200%200%201-2-2V5.5a2%202%200%200%201%202-2Z%22%2F%3E%3Cpath%20d%3D%22M14%203.5V8h4%22%2F%3E%3Cpath%20d%3D%22M8.5%2012.5h7M8.5%2015.5h4.5%22%2F%3E%3C%2Fsvg%3E");mask-image:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%20fill%3D%22none%22%20stroke%3D%22black%22%20stroke-width%3D%221.9%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpath%20d%3D%22M7%203.5h7l4%204V17a2%202%200%200%201-2%202H7a2%202%200%200%201-2-2V5.5a2%202%200%200%201%202-2Z%22%2F%3E%3Cpath%20d%3D%22M14%203.5V8h4%22%2F%3E%3Cpath%20d%3D%22M8.5%2012.5h7M8.5%2015.5h4.5%22%2F%3E%3C%2Fsvg%3E")}
/* ---- on a laptop --------------------------------------------------------- */
/* The phone layout is a 620px column, which on a 1440px screen is a narrow strip stranded
   in the middle with the navigation bar stretched across the whole width behind it. From
   900px up the bar becomes a left rail and the content moves over beside it, which is what
   a desktop application looks like. Nothing about the phone layout changes. */
@media (min-width: 900px){
  div[data-baseweb="tab-list"]{
    top:0;bottom:0;right:auto;width:216px;height:100vh;
    flex-direction:column;justify-content:flex-start;gap:.2rem;
    padding:1.3rem .7rem;border-top:none;border-right:1px solid var(--line);
    background:var(--card);backdrop-filter:none;-webkit-backdrop-filter:none;
    box-shadow:none}
  div[data-baseweb="tab-list"] button{
    flex:0 0 auto;width:100%;flex-direction:row;justify-content:flex-start;
    gap:.65rem;padding:.6rem .7rem!important;border-radius:10px}
  div[data-baseweb="tab-list"] button[aria-selected="true"]{background:var(--accent-soft)}
  div[data-baseweb="tab-list"] button p{font-size:14px!important}
  div[data-baseweb="tab-list"] button::before{width:19px;height:19px}

  /* The rail is fixed, so the page has to be moved out from under it - but only when
     there is a rail. The sign-in screen draws no tabs, and indenting it by 216px left the
     form floating off to one side of an empty page. */
  .stApp:has(div[data-baseweb="tab-list"]) .block-container{
    max-width:860px!important;padding:1.6rem 2rem 2rem calc(216px + 2rem)!important}
  .stApp:not(:has(div[data-baseweb="tab-list"])) .block-container{
    max-width:420px!important;padding:3.5rem 1rem 2rem!important}
  div[data-baseweb="tab-panel"]{padding-bottom:1rem}

  /* room to breathe, and the emergency card stops looking like a phone widget */
  .idcard{padding:1.5rem 1.6rem 1.6rem}
  .idcard .who{font-size:27px}
  .idcard .cell .v{font-size:17px}
}

/* On a wide laptop the record list is a single long column of short cards, which wastes
   half the screen. Two columns from 1200px, with the cards still whole. */
@media (min-width: 1200px){
  .stApp:has(div[data-baseweb="tab-list"]) .block-container{max-width:1040px!important}
  .reclist{display:grid;grid-template-columns:1fr 1fr;gap:.6rem;align-items:start}
  .reclist .rec,.reclist .med{margin-bottom:0}
}

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

