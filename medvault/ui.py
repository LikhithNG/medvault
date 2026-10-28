#!/usr/bin/env python3
"""Everything the screen looks like, in one place.

Three surfaces share one visual system:

  * the landing page a signed-out visitor lands on, which has to read as a product rather
    than as a login box floating on grey,
  * the app itself on a phone, where the navigation is a bar under the thumb,
  * the same app on a laptop, where that bar becomes a rail down the left and the brand
    sits at the top of it.

The test is not "does it look nice". It is "can someone hold this up at a hospital desk
and have the person behind it read it", which rules out most of what a dashboard normally
does: small type, dense tables, colour-only meaning.
"""
import html

import logo

_MARK_MASK = logo.css_url(logo.mark(size=48, uid="m", fill="mono").replace(
    "currentColor", "black"))

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root{
  --ink:#0B1220; --soft:#55606E; --faint:#8A95A5;
  --line:#E4E9F0; --line-soft:#EFF3F8;
  --bg:#F6F8FC; --card:#FFFFFF;
  --accent:#0F6FDE; --accent-bright:#3B8CFF; --accent-deep:#0A4E9E;
  --accent-soft:#EAF2FE;
  --warn:#B45309; --warn-soft:#FEF6E7;
  --danger:#B42318; --danger-soft:#FEF0EF;
  --ok:#067647; --ok-soft:#ECFDF3;
  --sans:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --sh-sm:0 1px 2px rgba(11,18,32,.05);
  --sh-md:0 4px 18px rgba(11,18,32,.07);
  --sh-lg:0 20px 50px rgba(11,18,32,.13);
  --r:14px; --r-lg:18px; --r-xl:24px;
}

.stApp{background:var(--bg)}
html,body,[class*="css"]{font-family:var(--sans)}
.block-container{padding:1rem .9rem 4rem!important;max-width:620px}
#MainMenu,footer,header{visibility:hidden}
h1,h2,h3,h4{font-family:var(--sans);color:var(--ink);letter-spacing:-.025em}

/* The signed-out page is the shop window, so it gets a wash of brand colour behind the
   headline. The selector is "there is no navigation on this page", which is true of the
   landing page and of nothing else. */
.stApp:not(:has([role="tablist"])){
  background:
    radial-gradient(900px 460px at 12% -12%,rgba(59,140,255,.16),transparent 62%),
    radial-gradient(760px 420px at 92% 2%,rgba(15,111,222,.10),transparent 60%),
    var(--bg)}

/* ---- the lockup ---------------------------------------------------------- */
.mvlockup{display:inline-flex;align-items:center;gap:.5rem;text-decoration:none}
.mvlockup .mvmark{display:block;flex:0 0 auto}
.mvname{font-weight:800;font-size:19px;letter-spacing:-.035em;
  line-height:1;white-space:nowrap}

/* ---- the bar at the top of the app --------------------------------------- */
.appbar{margin:0 0 1rem}
.appbar .top{display:flex;align-items:center;gap:.6rem;margin-bottom:.7rem}
.appbar .count{margin-left:auto;font-size:11px;font-weight:700;letter-spacing:.04em;
  text-transform:uppercase;color:var(--accent);background:var(--accent-soft);
  border:1px solid #D6E6FD;border-radius:999px;padding:.25rem .6rem;white-space:nowrap}

/* the signed-in strip. Named .whoami because .who is already the provider line inside a
   record card, and reusing it wrapped every hospital name in something that looked like
   an editable field. */
.whoami{display:flex;align-items:center;gap:.6rem;background:var(--card);
  border:1px solid var(--line);border-radius:var(--r);padding:.6rem .75rem;
  box-shadow:var(--sh-sm)}
.whoami .av{width:32px;height:32px;border-radius:10px;color:#fff;flex:0 0 auto;
  background:linear-gradient(135deg,var(--accent-bright),var(--accent-deep));
  display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px}
.whoami .nm{font-size:14.5px;font-weight:700;color:var(--ink);line-height:1.2}
.whoami .rl{font-size:11.5px;color:var(--faint);margin-top:.1rem}
.whoami .count{margin-left:auto;font-size:10.5px;font-weight:700;
  text-transform:uppercase;letter-spacing:.05em;color:var(--accent);
  background:var(--accent-soft);border:1px solid #D6E6FD;padding:.22rem .55rem;
  border-radius:999px;white-space:nowrap}
.whoami .count+.chk{margin-left:.4rem}
.whoami .chk{margin-left:auto;font-size:10.5px;font-weight:700;text-transform:uppercase;
  letter-spacing:.05em;color:var(--ok);background:var(--ok-soft);border:1px solid #BCE5CF;
  padding:.22rem .55rem;border-radius:999px;text-align:right;line-height:1.3}

/* ---- the landing page ---------------------------------------------------- */
.navbar{display:flex;align-items:center;gap:.6rem;padding:.2rem 0 1.4rem;margin-bottom:.4rem}
.navbar .links{margin-left:auto;display:flex;align-items:center;gap:1.1rem}
.navbar .links span{font-size:13px;font-weight:600;color:var(--soft)}
.navbar .links .free{font-size:11.5px;font-weight:700;letter-spacing:.04em;
  text-transform:uppercase;color:var(--ok);background:var(--ok-soft);
  border:1px solid #BCE5CF;border-radius:999px;padding:.28rem .65rem}

.eyebrow{display:inline-flex;align-items:center;gap:.42rem;font-size:11.5px;font-weight:700;
  letter-spacing:.07em;text-transform:uppercase;color:var(--accent);
  background:rgba(255,255,255,.75);border:1px solid #D6E6FD;border-radius:999px;
  padding:.33rem .7rem;margin-bottom:1rem;box-shadow:var(--sh-sm)}
.eyebrow i{width:6px;height:6px;border-radius:50%;background:var(--accent);
  display:inline-block;box-shadow:0 0 0 3px rgba(15,111,222,.18)}

.hero h1{font-size:40px;line-height:1.06;font-weight:800;letter-spacing:-.045em;
  color:var(--ink);margin:0 0 .85rem}
.hero h1 em{font-style:normal;
  background:linear-gradient(100deg,var(--accent-bright),var(--accent-deep));
  -webkit-background-clip:text;background-clip:text;color:transparent}
.hero p.lead{font-size:16.5px;line-height:1.6;color:var(--soft);margin:0 0 1.2rem;
  max-width:36ch}
.ticks{display:flex;flex-wrap:wrap;gap:.45rem;margin-bottom:.2rem}
.ticks span{display:inline-flex;align-items:center;gap:.35rem;font-size:12.5px;
  font-weight:600;color:var(--ink);background:var(--card);border:1px solid var(--line);
  border-radius:999px;padding:.34rem .7rem;box-shadow:var(--sh-sm)}
.ticks svg{flex:0 0 auto}

/* the sign-in box. Streamlit draws the widgets, so the frame is put round them by
   finding the container that holds this marker. */
.panelmark{display:none}
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div >
  div[data-testid="stVerticalBlock"] > div[data-testid="element-container"] >
  div[data-testid="stMarkdown"] .panelmark),
div[data-testid="stVerticalBlock"]:not([data-testid="stVerticalBlockBorderWrapper"] *):has(
  > .element-container .panelmark){
  background:var(--card);border:1px solid var(--line)!important;border-radius:var(--r-xl);
  box-shadow:var(--sh-lg);padding:1.35rem 1.25rem 1.1rem!important}
.panelhead{font-size:19px;font-weight:800;letter-spacing:-.03em;color:var(--ink);
  margin-bottom:.15rem}
.panelsub{font-size:13px;color:var(--faint);line-height:1.5;margin-bottom:.9rem}

.feature{background:var(--card);border:1px solid var(--line);border-radius:var(--r-lg);
  padding:1.1rem 1.1rem 1.15rem;box-shadow:var(--sh-sm);height:100%}
.feature .ic{width:38px;height:38px;border-radius:11px;background:var(--accent-soft);
  color:var(--accent);display:flex;align-items:center;justify-content:center;
  margin-bottom:.75rem}
.feature h3{font-size:16.5px;font-weight:800;letter-spacing:-.025em;
  margin:0 0 .35rem!important;padding:0!important;line-height:1.3}
.feature p{font-size:13.5px;line-height:1.55;color:var(--soft);margin:0}

.steps{counter-reset:s;display:grid;gap:.55rem;margin-top:.2rem}
.step{display:flex;gap:.8rem;background:var(--card);border:1px solid var(--line);
  border-radius:var(--r);padding:.85rem .95rem;box-shadow:var(--sh-sm)}
.step .n{counter-increment:s;flex:0 0 auto;width:26px;height:26px;border-radius:9px;
  background:var(--ink);color:#fff;font-size:12.5px;font-weight:800;display:flex;
  align-items:center;justify-content:center}
.step .n::before{content:counter(s)}
.step h4{font-size:14.5px;font-weight:700;margin:.1rem 0 .2rem!important;
  padding:0!important;letter-spacing:-.02em;line-height:1.3}
.step p{font-size:13px;line-height:1.55;color:var(--soft);margin:0}

.sitefoot{margin-top:2.2rem;padding:1.4rem 0 .6rem;border-top:1px solid var(--line);
  color:var(--faint);font-size:12.5px;line-height:1.65}
.sitefoot .mvlockup{color:var(--faint);margin-bottom:.55rem;opacity:.85}
.sitefoot .mvname{font-size:15px;color:var(--soft)}
.sitefoot b{color:var(--soft);font-weight:600}

/* ---- the emergency card -------------------------------------------------- */
.idcard{background:linear-gradient(150deg,#2E86FF 0%,#0F6FDE 45%,#083F80 100%);color:#fff;
  border-radius:var(--r-xl);padding:1.25rem 1.25rem 1.3rem;margin-bottom:.9rem;
  position:relative;overflow:hidden;box-shadow:0 14px 34px rgba(12,76,160,.30)}
/* a soft highlight across the top, so the card has a surface rather than a flat fill */
.idcard::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(120% 70% at 85% -10%,rgba(255,255,255,.24),transparent 60%)}
.idcard>*{position:relative;z-index:1}
.idcard .brandline{display:flex;align-items:center;gap:.4rem;font-size:11px;font-weight:700;
  letter-spacing:.12em;text-transform:uppercase;opacity:.78;margin-bottom:.85rem}
.idcard .who{font-size:24px;font-weight:800;letter-spacing:-.035em;line-height:1.14}
.idcard .sub{font-size:13px;opacity:.87;margin-top:.18rem}
.idcard .grid{display:flex;gap:.5rem;margin-top:1rem}
.idcard .cell{background:rgba(255,255,255,.16);border-radius:12px;padding:.52rem .62rem;
  flex:1 1 0;min-width:0;backdrop-filter:blur(2px)}
.idcard .cell .k{font-size:10px;text-transform:uppercase;letter-spacing:.07em;opacity:.82}
/* A date of birth is ten characters and was wrapping onto two lines inside its cell, which
   made the card look broken. The cells share the width evenly and clip rather than wrap. */
.idcard .cell .v{font-size:15px;font-weight:700;margin-top:.12rem;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
/* On a phone the three cells are about 75px of text each, and the date of birth - the
   longest thing on the card and the one a desk most needs - was cut to "1998-0...". It
   gets the room; "O+" and a record count do not need theirs. */
@media (max-width: 480px){ .idcard .cell:nth-child(2){flex-grow:1.8} }

/* a red band, because an allergy is the one thing that must not be missed */
.alert{background:var(--danger-soft);border:1px solid #F6C9C4;border-left:4px solid var(--danger);
  border-radius:var(--r);padding:.75rem .9rem;margin-bottom:.8rem}
.alert .k{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;
  color:var(--danger)}
.alert .v{font-size:15.5px;font-weight:600;color:#7A1710;margin-top:.15rem;line-height:1.35}

/* ---- a record in the timeline -------------------------------------------- */
.rec{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
  padding:.85rem .95rem;margin-bottom:.6rem;box-shadow:var(--sh-sm);
  transition:box-shadow .16s ease,transform .16s ease,border-color .16s ease}
.rec:hover{box-shadow:var(--sh-md);border-color:#D7DFEA}
.rec:active{transform:scale(.995)}
.rec .top{display:flex;align-items:center;gap:.4rem;margin-bottom:.35rem;flex-wrap:wrap}
.rec .pill{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
  padding:.2rem .5rem;border-radius:999px;background:var(--accent-soft);color:var(--accent);
  border:1px solid #D6E6FD}
.rec .when{font-size:12px;color:var(--faint);margin-left:auto;white-space:nowrap}
.rec .title{font-size:16.5px;font-weight:700;color:var(--ink);line-height:1.3;
  letter-spacing:-.02em}
.rec .who{font-size:13px;color:var(--soft);margin-top:.12rem}
.rec .sum{font-size:13.5px;color:var(--soft);margin-top:.42rem;line-height:1.45}
.rec .nofile{font-size:12px;color:var(--faint);margin-top:.4rem}

/* ---- where a record came from -------------------------------------------- */
/* The badge is the product's whole answer to "how do I know this is real". It is drawn on
   every record, including the unverified ones, because a vault that only labels the good
   records teaches people that an absent badge means nothing. */
.prov{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
  padding:.2rem .5rem;border-radius:999px;display:inline-flex;align-items:center;gap:.25rem}
.prov.self{background:#F2F4F8;color:#5B6673;border:1px solid #DFE4EC}
.prov.verified{background:var(--ok-soft);color:var(--ok);border:1px solid #BCE5CF}
.prov.clinical{background:var(--accent-soft);color:var(--accent);border:1px solid #CFE3FB}
.provwhy{font-size:12px;color:var(--faint);margin-top:.35rem;line-height:1.45}

/* ---- a medicine ---------------------------------------------------------- */
.med{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
  padding:.85rem .95rem;margin-bottom:.55rem;border-left:4px solid var(--accent);
  box-shadow:var(--sh-sm)}
.med .n{font-size:16px;font-weight:700;color:var(--ink);line-height:1.3;letter-spacing:-.02em}
.med .d{font-size:13.5px;color:var(--soft);margin-top:.25rem;line-height:1.45}
.med .why{font-size:12.5px;color:var(--faint);margin-top:.3rem;font-style:italic}

/* ---- the bill cross-check ------------------------------------------------ */
.hit{border-radius:var(--r);padding:.9rem .95rem;margin-bottom:.6rem;border:1px solid}
.hit.bad{background:var(--danger-soft);border-color:#F6C9C4;border-left:4px solid var(--danger)}
.hit.warn{background:var(--warn-soft);border-color:#F7E0B5;border-left:4px solid var(--warn)}
.hit.ok{background:var(--ok-soft);border-color:#C4E9D5;border-left:4px solid var(--ok)}
.hit .h{font-size:14.5px;font-weight:700;margin-bottom:.2rem;letter-spacing:-.015em}
.hit.bad .h{color:#7A1710} .hit.warn .h{color:#7A4A06} .hit.ok .h{color:#05502F}
.hit .b{font-size:13.5px;color:#333B45;line-height:1.5}
.hit .amt{float:right;font-weight:800;font-size:16px;margin-left:.75rem;
  padding-left:.15rem}

/* ---- the question and answer thread -------------------------------------- */
.qa{margin-bottom:1rem}
.bubble{border-radius:16px;padding:.75rem .95rem;font-size:14.5px;line-height:1.58;
  width:fit-content;max-width:92%}
.bubble.q{background:linear-gradient(135deg,var(--accent-bright),var(--accent-deep));
  color:#fff;margin-left:auto;border-bottom-right-radius:5px;font-weight:500;
  box-shadow:0 5px 16px rgba(15,111,222,.26)}
.bubble.a{background:var(--card);border:1px solid var(--line);color:var(--ink);
  border-bottom-left-radius:5px;box-shadow:var(--sh-sm);margin-top:.5rem}
.bubble.a p{margin:0 0 .6rem}
.bubble.a p:last-child{margin:0}
/* The badge is the whole point of the answer: a reader has to be able to tell at a glance
   whether what follows came out of their own records or out of a model's general
   knowledge, and those two things look identical once they are prose. */
.badge{display:inline-flex;align-items:center;gap:.3rem;font-size:10.5px;font-weight:700;
  text-transform:uppercase;letter-spacing:.055em;padding:.22rem .55rem;border-radius:999px;
  margin-bottom:.55rem}
.badge.ok{background:var(--ok-soft);color:var(--ok);border:1px solid #BCE5CF}
.badge.warn{background:var(--warn-soft);color:var(--warn);border:1px solid #F7E0B5}
.badge.bad{background:var(--danger-soft);color:var(--danger);border:1px solid #F6C9C4}
.srcs{font-size:12px;color:var(--faint);margin-top:.6rem;padding-top:.55rem;
  border-top:1px dashed var(--line);line-height:1.5}
.srcs b{color:var(--soft);font-weight:600}

/* ---- small shared bits --------------------------------------------------- */
.sect{display:flex;align-items:center;gap:.45rem;font-size:11.5px;font-weight:700;
  text-transform:uppercase;letter-spacing:.09em;color:var(--soft);margin:1.4rem 0 .6rem}
.sect::before{content:"";width:3px;height:13px;border-radius:2px;flex:0 0 auto;
  background:linear-gradient(var(--accent-bright),var(--accent-deep))}
.empty{background:var(--card);border:1px dashed #D8E0EA;border-radius:var(--r-lg);
  padding:1.7rem 1rem;text-align:center;color:var(--faint);font-size:14px;line-height:1.55}
.note{font-size:12.5px;color:var(--faint);line-height:1.55;margin-top:.5rem}

/* ---- Streamlit's own widgets --------------------------------------------- */
/* Download buttons are a different Streamlit widget, and were left out of this: the
   calendar file - the thing that actually reminds anybody - sat under the Medicines
   screen as the one square, flat-blue button in the app. */
:is(.stButton,.stDownloadButton)>button{border-radius:12px;font-weight:600;
  font-family:var(--sans);border:1px solid var(--line);padding:.58rem 1rem;
  background:var(--card);color:var(--ink);
  transition:box-shadow .15s ease,transform .1s ease,border-color .15s ease}
:is(.stButton,.stDownloadButton)>button:hover{border-color:#C9D6E6;box-shadow:var(--sh-sm);
  color:var(--accent)}
:is(.stButton,.stDownloadButton)>button:active{transform:translateY(1px)}
/* Streamlit 1.5x+ sets a button's label on one line and cuts it with an ellipsis, which
   turned the example questions on the Ask screen into "What is each of my medici...". A
   button that says less than it does is worse than a taller one. */
:is(.stButton,.stDownloadButton,[data-testid="stFormSubmitButton"]) button
  [data-testid="stMarkdownContainer"]{white-space:normal!important;overflow:visible!important;
  text-overflow:clip!important;height:auto!important}
:is(.stButton,.stDownloadButton,[data-testid="stFormSubmitButton"]) button p{
  white-space:normal!important;line-height:1.35}
:is(.stButton,.stDownloadButton)>button[kind="primary"],
button[kind="primaryFormSubmit"]{
  background:linear-gradient(135deg,var(--accent-bright),var(--accent-deep));
  border:none;color:#fff;box-shadow:0 6px 18px rgba(15,111,222,.30)}
:is(.stButton,.stDownloadButton)>button[kind="primary"]:hover,
button[kind="primaryFormSubmit"]:hover{
  box-shadow:0 10px 24px rgba(15,111,222,.38);color:#fff}
div[data-testid="stFileUploader"]{background:var(--card);border-radius:var(--r);
  border:1px dashed #D8E0EA;padding:.55rem}
div[data-testid="stFileUploader"] section{background:transparent;border:none}

/* The stock info box is red-tinted by default; make it match the rest. */
div[data-testid="stAlert"]{border-radius:12px;font-size:13.5px;background:var(--accent-soft);
  border:1px solid #CFE3FB}
div[data-testid="stAlert"] *{color:#0B4F9E!important}

/* Inputs. Streamlit inherits the viewer's dark-mode preference, which turned the paste box
   black with black text on a page that is otherwise light. Pinned explicitly. */
textarea,input[type="text"],input[type="password"],div[data-baseweb="textarea"],
div[data-baseweb="input"],div[data-baseweb="select"]>div,
[data-testid="stTextInputRootElement"],[data-testid="stTextAreaRootElement"],
[data-testid="stTimeInputTimeDisplay"],div[role="group"]:has(> input[role="combobox"]){
  background:var(--card)!important;color:var(--ink)!important;border-radius:11px!important;
  border-color:var(--line)!important;font-family:var(--sans)!important;
  font-size:14.5px!important}
div[data-baseweb="input"]:focus-within,div[data-baseweb="textarea"]:focus-within,
[data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stTextAreaRootElement"]:focus-within,
[data-testid="stTimeInputTimeDisplay"]:focus-within,
div[role="group"]:has(> input[role="combobox"]):focus-within{
  border-color:var(--accent)!important;box-shadow:0 0 0 3px rgba(15,111,222,.14)}
textarea::placeholder,input::placeholder{color:var(--faint)!important}

/* Captions carry most of the plain-language explanation in this app; they have to be read,
   not merely present. */
div[data-testid="stCaptionContainer"],div[data-testid="stCaptionContainer"] p{
  color:var(--soft)!important;font-size:13px!important;line-height:1.5!important}
label p{color:var(--soft)!important;font-size:13px!important;font-weight:600!important}

/* One typeface. Streamlit sets Source Sans on its own elements through generated class
   names, so the Inter rule at the top reached the buttons and the inputs and missed the
   captions, the cards and the section headings - two typefaces on every screen, which
   reads as two products. The icon font and the letter's fixed-width text are left alone -
   the letter lines its figures up with spaces, so it is excluded with everything inside
   it, not only its wrapper (the fixed-width font is on an inner div). */
/* One compound selector, on one line on purpose: a line break between two :not()s is a
   descendant combinator, and that version matched everything inside any element - the
   password field's eye icon included, which printed the word "visibility". */
.stApp :is(p,li,span,div,label,b,strong,em,small,a,h1,h2,h3,h4,h5,h6,summary,button,input,textarea):not([data-testid="stIconMaterial"]):not([data-testid="stText"]):not([data-testid="stText"] *){
  font-family:var(--sans)}

/* The three totals on a checked bill. Streamlit draws a metric as a 36px number in a
   light weight, which next to everything else here looked like it came from another
   site. They are cards, in the type the cards use. */
div[data-testid="stMetric"]{background:var(--card);border:1px solid var(--line);
  border-radius:var(--r);padding:.75rem .9rem .8rem;box-shadow:var(--sh-sm)}
div[data-testid="stMetricLabel"] p{font-size:10.5px!important;font-weight:700!important;
  text-transform:uppercase;letter-spacing:.07em;color:var(--faint)!important}
div[data-testid="stMetricValue"]{font-size:23px!important;font-weight:800!important;
  letter-spacing:-.035em;color:var(--ink);line-height:1.25}
/* the unexplained gap is a question to ask, so it takes the warning colour, not the
   alarm one - the caption under it says in words that it is not money owed */
:is(div[data-testid="column"],div[data-testid="stColumn"]):last-child
  div[data-testid="stMetricValue"]{color:var(--warn)}

/* ---- the navigation bar -------------------------------------------------- */
/* Streamlit draws tabs as a strip at the top of the page, which reads as a web page.
   Fixed to the bottom with an icon above each label, it reads as an app - and on a phone
   it also puts the controls where a thumb already is. The icons are masks rather than
   background images so they take their colour from the active state. */
[role="tablist"]{
  position:fixed;left:0;right:0;bottom:0;z-index:999;
  display:flex;gap:0;padding:.35rem .25rem calc(.35rem + env(safe-area-inset-bottom));
  background:rgba(255,255,255,.92);backdrop-filter:saturate(180%) blur(14px);
  -webkit-backdrop-filter:saturate(180%) blur(14px);
  border-top:1px solid var(--line);border-radius:0;margin:0;
  box-shadow:0 -2px 18px rgba(16,21,28,.06);
  /* Streamlit 1.5x+ makes the tab list a scroll box and scrolls it to keep the chosen
     tab in view - which scrolled the brand drawn at the top of the rail half out of
     sight. Six tabs always fit, so there is nothing to scroll. */
  overflow:visible!important}
[role="tablist"] [role="tab"]{
  flex:1 1 0;min-width:0;border-radius:10px;background:transparent!important;
  padding:.3rem .1rem .25rem!important;display:flex;flex-direction:column;
  align-items:center;gap:.18rem}
[role="tablist"] [role="tab"] p{
  font-family:var(--sans)!important;font-size:10.5px!important;font-weight:600!important;
  color:var(--faint)!important;margin:0;letter-spacing:-.01em;white-space:nowrap}
[role="tablist"] [role="tab"][aria-selected="true"] p{color:var(--accent)!important}
/* Six labels across a phone is 62px each, and at 10.5px "Records" and "Medicines" met in
   the middle with no space between them. Smaller, and clipped rather than overlapping. */
[role="tablist"]:has([role="tab"]:nth-child(6)) [role="tab"] p{
  font-size:9.5px!important;letter-spacing:-.02em;max-width:100%;overflow:hidden;
  text-overflow:ellipsis}
div[data-baseweb="tab-highlight"],div[data-baseweb="tab-border"],
.react-aria-SelectionIndicator,[role="tablist"]::after{display:none}

/* one icon per position, drawn above the label */
[role="tablist"] [role="tab"]::before{
  content:"";width:21px;height:21px;display:block;background:var(--faint);
  -webkit-mask-size:contain;mask-size:contain;-webkit-mask-repeat:no-repeat;
  mask-repeat:no-repeat;-webkit-mask-position:center;mask-position:center}
[role="tablist"] [role="tab"][aria-selected="true"]::before{background:var(--accent)}

/* the panel has to clear the bar, or the last record sits underneath it */
[role="tabpanel"]{padding-bottom:4.6rem}

/* There is exactly one tab group in this app and it is the navigation. The sign-in screen
   uses a radio precisely so that stays true - a second group would be pinned to the bottom
   of the screen wearing navigation icons. */

__ICONS__

/* ---- on a laptop --------------------------------------------------------- */
/* The phone layout is a 620px column, which on a 1440px screen is a narrow strip stranded
   in the middle with the navigation bar stretched across the whole width behind it. From
   900px up the bar becomes a left rail with the brand at the top of it, and the content
   moves over beside it. Nothing about the phone layout changes. */
@media (min-width: 900px){
  [role="tablist"]{
    top:0;bottom:0;right:auto;width:228px;height:100vh;
    flex-direction:column;justify-content:flex-start;gap:.2rem;
    padding:4.9rem .75rem 1.3rem;border-top:none;border-right:1px solid var(--line);
    background:var(--card);backdrop-filter:none;-webkit-backdrop-filter:none;
    box-shadow:none}
  /* the brand, drawn into the top of the rail: the mark as a mask, the name as text */
  [role="tablist"]::before{
    content:"";position:absolute;top:1.5rem;left:1.1rem;width:30px;height:30px;
    background:linear-gradient(135deg,var(--accent-bright),var(--accent-deep));
    -webkit-mask-image:__MARK__;mask-image:__MARK__;
    -webkit-mask-size:contain;mask-size:contain;
    -webkit-mask-repeat:no-repeat;mask-repeat:no-repeat}
  /* Streamlit 1.5x+ draws its tab underline as this same ::after - 2px high, full width,
     grey - and it showed as a line struck through the name. Every box property is reset,
     not only the ones the name needs. */
  [role="tablist"]::after{
    content:"MedVault";position:absolute;top:1.78rem;left:3.45rem;font-weight:800;
    font-size:19px;letter-spacing:-.035em;color:var(--ink);line-height:1;
    right:auto;bottom:auto;width:auto;height:auto;background:none!important;border:0;
    display:block}
  [role="tablist"] [role="tab"]{
    flex:0 0 auto;width:100%;flex-direction:row;justify-content:flex-start;
    gap:.7rem;padding:.62rem .7rem!important;border-radius:11px}
  /* !important because the phone rules above set these with it - which is also why, for
     as long as this rail has existed, the chosen tab had no highlight and the labels
     stayed at the phone's 9.5px */
  [role="tablist"] [role="tab"]:hover{background:var(--line-soft)!important}
  [role="tablist"] [role="tab"][aria-selected="true"]{background:var(--accent-soft)!important}
  [role="tablist"] [role="tab"] p,
  [role="tablist"]:has([role="tab"]:nth-child(6)) [role="tab"] p{
    font-size:14px!important;max-width:none;overflow:visible}
  [role="tablist"] [role="tab"]::before{width:19px;height:19px}

  /* The rail is fixed, so the page has to be moved out from under it - but only when
     there is a rail. The landing page draws no tabs, and indenting it by 228px left the
     hero floating off to one side of an empty page. */
  .stApp:has([role="tablist"]) .block-container{
    max-width:880px!important;padding:1.6rem 2rem 2rem calc(228px + 2rem)!important}
  .stApp:not(:has([role="tablist"])) .block-container{
    max-width:1060px!important;padding:2.2rem 2rem 2rem!important}
  [role="tabpanel"]{padding-bottom:1rem}

  /* the lockup in the page header is the rail's job up here */
  .appbar .top{display:none}

  /* room to breathe, and the emergency card stops looking like a phone widget */
  .idcard{padding:1.6rem 1.7rem 1.7rem}
  .idcard .who{font-size:28px}
  .idcard .cell .v{font-size:17px}

  .hero h1{font-size:52px}
  .hero p.lead{font-size:17.5px}
  .navbar{padding:.2rem 0 2rem}
}

/* Streamlit's columns do not stack on a narrow screen, so the landing page's two-column
   hero is told to. Scoped to the landing page: the button pairs inside the app are two
   columns on purpose and should stay side by side. */
@media (max-width: 899px){
  .stApp:not(:has([role="tablist"])) div[data-testid="stHorizontalBlock"]{
    flex-direction:column;gap:.6rem}
  .stApp:not(:has([role="tablist"])) :is(div[data-testid="column"],div[data-testid="stColumn"]){
    width:100%!important;flex:1 1 100%!important;min-width:0!important}
  .hero h1{font-size:33px}
}

/* A little more room again on a wide screen. The record list stays one column: each card
   is its own st.markdown call, so there is no single element a grid could live on. */
@media (min-width: 1200px){
  .stApp:has([role="tablist"]) .block-container{max-width:1000px!important}
}

</style>
"""

# The navigation icons, kept out of the stylesheet above so the shape of the page stays
# readable. Which set appears is inferred from the number of tabs the role drew.
_NAV = {
    6: [  # patient: card, add, records, medicines, bill, ask
        '<rect x="2.5" y="4.5" width="19" height="15" rx="3"/><path d="M12 15.2s-3.1-2-3.1-4a1.8 1.8 0 0 1 3.1-1.2 1.8 1.8 0 0 1 3.1 1.2c0 2-3.1 4-3.1 4Z"/>',
        '<path d="M3 8.5h3l1.6-2.2h8.8L18 8.5h3v10H3z"/><circle cx="12" cy="13" r="3.4"/>',
        '<path d="M7 3.5h7l4 4V17a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5.5a2 2 0 0 1 2-2Z"/><path d="M14 3.5V8h4"/><path d="M8.5 12.5h7M8.5 15.5h4.5"/>',
        '<rect x="3.2" y="8.6" width="17.6" height="6.8" rx="3.4" transform="rotate(-40 12 12)"/><path d="M9.6 9.6l4.8 4.8"/>',
        '<path d="M6 3.5h12v17l-2-1.4-2 1.4-2-1.4-2 1.4-2-1.4-2 1.4z"/><path d="M9 8h6M9 11.5h6M9 15h3.5"/>',
        '<path d="M12 3.8c-4.6 0-8.4 3.1-8.4 7s3.8 7 8.4 7c.7 0 1.3 0 1.9-.2l3.6 2.1v-3.8c1.7-1.3 2.9-3.1 2.9-5.1 0-3.9-3.8-7-8.4-7Z"/><path d="M12 12.9v-.3c0-.9.5-1.3 1.1-1.8.5-.4.9-.9.9-1.5a2 2 0 0 0-4 0"/><path d="M12 15.1h.01"/>',
    ],
    2: [  # clinician: review, records
        '<path d="M7 3.5h10a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5.5a2 2 0 0 1 2-2Z"/><path d="M8.8 12.2l2.2 2.2 4.2-4.6"/>',
        '<path d="M7 3.5h7l4 4V17a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5.5a2 2 0 0 1 2-2Z"/><path d="M14 3.5V8h4"/><path d="M8.5 12.5h7M8.5 15.5h4.5"/>',
    ],
}


def _stroke_svg(body, width=1.9):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="black" stroke-width="{width}" stroke-linecap="round" '
            f'stroke-linejoin="round">{body}</svg>')


def _nav_css():
    out = []
    for count, icons in _NAV.items():
        # six tabs means a patient, two means a clinician; the stylesheet can tell them
        # apart by asking whether a sixth button exists.
        scope = ('[role="tablist"]:has([role="tab"]:nth-child(6))' if count == 6
                 else '[role="tablist"]:not(:has([role="tab"]:nth-child(3)))')
        for i, body in enumerate(icons, start=1):
            url = logo.css_url(_stroke_svg(body))
            out.append(f'{scope} [role="tab"]:nth-child({i})::before'
                       f'{{-webkit-mask-image:{url};mask-image:{url}}}')
    return "\n".join(out)


CSS = CSS.replace("__ICONS__", _nav_css()).replace("__MARK__", _MARK_MASK)


# ------------------------------------------------------------------ pieces ----

def lockup(size=19):
    return logo.wordmark(size=size)


def appbar(strip=""):
    """The top of every signed-in screen: the brand, and who is looking at it. One block
    rather than two, because on a laptop the rail already carries the brand and what is
    left has to close up behind it rather than leave a gap."""
    return f"<div class='appbar'><div class='top'>{lockup()}</div>{strip}</div>"


def section(label):
    return f"<div class='sect'>{label}</div>"


def empty(message):
    return f"<div class='empty'>{message}</div>"


_TO_TOP = """<script>
(function () {
  var doc = window.parent.document;
  function settle() {
    if (doc.activeElement && doc.activeElement !== doc.body) doc.activeElement.blur();
    doc.querySelectorAll("*").forEach(function (el) { if (el.scrollTop > 0) el.scrollTop = 0; });
  }
  settle(); setTimeout(settle, 250); setTimeout(settle, 800);
})();
</script>"""


def to_top():
    """Start the next screen at its top, with nothing focused.

    Signing in swaps the whole page. React kept the focused password box and reused it as
    a text field further down the new screen, so the browser scrolled there: the Card
    screen opened halfway down, past the emergency card - and on a phone, with the
    keyboard up. Signing out did the same to the landing page. Called once, on the run
    after either.
    """
    import streamlit.components.v1 as components
    components.html(_TO_TOP, height=0, width=0)


def safe(text):
    """Text for inside a chat bubble: escaped, with bold let back through.

    A model's answer, a question and a record title read off a scan all went into the
    page as raw HTML. Bold is the one tag the fixed answers use on purpose - the emergency
    answer bolds "call 911" - so it is the one tag restored.
    """
    return (html.escape(str(text or "")).replace("&lt;b&gt;", "<b>")
            .replace("&lt;/b&gt;", "</b>"))


PROV_CLASS = {"SELF": "self", "VERIFIED": "verified", "CLINICAL": "clinical"}


def provenance_badge(record):
    """The badge for one record. Always drawn, including for unverified records."""
    import accounts
    prov = record.get("provenance") or "SELF"
    label = accounts.PROVENANCE.get(prov, accounts.PROVENANCE["SELF"])[0]
    return f"<span class='prov {PROV_CLASS.get(prov, 'self')}'>{label}</span>"


def signed_in_strip(account, meta=""):
    import accounts
    initials = "".join(w[0] for w in (account.get("display_name") or
                                      account.get("email", "?")).split()[:2]).upper()
    role = ("Clinician" if account["role"] == "clinician" else "Patient")
    count = f"<div class='count'>{meta}</div>" if meta else ""
    chk = ""
    if accounts.is_verified_clinician(account):
        chk = (f"<div class='chk'>NPI {account['npi']} verified<br>"
               f"{account.get('npi_specialty') or ''}</div>")
    return (f"<div class='whoami'><div class='av'>{initials or '?'}</div>"
            f"<div><div class='nm'>{account.get('display_name') or account['email']}</div>"
            f"<div class='rl'>{role}</div></div>{count}{chk}</div>")


def mono_mark(size=13):
    """A small white mark, for use inside the emergency card's own header line."""
    return logo.mark(size=size, uid="b", fill="white")
