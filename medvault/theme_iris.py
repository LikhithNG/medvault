"""The Deep Iris theme, layered over ui.CSS and loaded after it so every rule here wins.

ui.CSS keeps the layout; this file decides the colour, type and corners. The mark's own
colours live in logo.py, which tools/make_icons.py also reads for the home-screen icons.

The palette comes from a brand token sheet (deep iris, clinical cyan, mint). Two of its
colours fail as text on white: fog #9494A9 is 2.9:1 and cyan #00B1FF about 2.6:1. So they
appear only as fills and on the dark surfaces, and the text tokens are darker steps of the
same hue, each at least 4.5:1 where it is used.

The signed-out page goes dark, on the deep iris canvas. The app itself stays light,
because an emergency card is read at a hospital desk; only its navigation rail and the
card turn iris.

Gilroy is a paid font, so it is named first for anyone who has it installed, and Manrope,
the closest free geometric sans on Google Fonts, stands in for everyone else.
"""

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

:root{
  --ink:#16165C; --soft:#45457A; --faint:#5E5E86;
  --line:#D8D8E3; --line-soft:#ECECF3;
  --bg:#F4F4F6; --card:#FFFFFF;
  --accent:#403CD5; --accent-bright:#5350CC; --accent-strong:#403CD5; --accent-deep:#16165C;
  --focus:#232269;
  --accent-soft:#EEEDFD;
  --sans:'Gilroy','Manrope',ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  --sh-sm:0 1px 2px rgba(22,22,92,.06);
  --sh-md:0 6px 20px rgba(22,22,92,.08);
  --sh-lg:0 24px 60px rgba(22,22,92,.18);
  --r:16px; --r-lg:24px; --r-xl:32px;
  --iris-canvas:#16165C; --iris-shadow:#232269; --iris-glow:#403CD5;
  --lilac:#B1A6F6; --cyan:#00B1FF; --mint:#00FFAA; --teal:#2EE9FF; --ash:#D8D8E3;
  --lilac-line:#D9D5FB;
}

/* The token sheet has two weights, 500 and 600, and tight tracking on headings. The old
   look leaned on 800, which in Manrope reads as shouting. */
h1,h2,h3,h4,.mvname,.panelhead,.feature h3,.step h4,.idcard .who,.rec .title,.med .n,
.whoami .nm,.ag-card .ag-n,.hit .h{font-weight:600!important;letter-spacing:-.03em}

/* ---- the signed-out page, on the deep iris canvas ---------------------------- */
.stApp:not(:has([role="tablist"])){
  background:
    radial-gradient(900px 560px at 8% -12%,rgba(64,60,213,.60),transparent 62%),
    radial-gradient(720px 480px at 96% 0%,rgba(0,177,255,.20),transparent 60%),
    radial-gradient(900px 520px at 50% 115%,rgba(0,255,170,.08),transparent 60%),
    var(--iris-canvas)}
/* the mark's gradient ends in iris shadow, which all but vanishes on the iris canvas;
   on the dark page it runs between the two brighter irises instead */
.navbar .mvmark stop:first-child,.sitefoot .mvmark stop:first-child{stop-color:#524FE1}
.navbar .mvmark stop:last-child,.sitefoot .mvmark stop:last-child{stop-color:#403CD5}
/* the wordmark carries its colours inline (logo.wordmark), so only !important reaches it */
.navbar .mvname{color:#FFFFFF!important}
.navbar .mvname span{color:var(--teal)!important}
.navbar .links .cta{background:#FFFFFF;color:var(--iris-canvas);box-shadow:none;
  padding:.55rem 1.1rem}
.navbar .links .cta:hover{box-shadow:0 0 0 4px rgba(177,166,246,.25)}
.navbar .links .free{color:var(--mint);background:rgba(0,255,170,.08);
  border-color:rgba(0,255,170,.35)}
.eyebrow{color:var(--lilac);background:rgba(255,255,255,.06);
  border-color:rgba(177,166,246,.35);box-shadow:none}
.eyebrow i{background:var(--mint);box-shadow:0 0 0 3px rgba(0,255,170,.20)}
.hero h1{color:#FFFFFF;letter-spacing:-.04em;line-height:1}
.hero h1 em{background:linear-gradient(100deg,var(--teal),var(--mint));
  -webkit-background-clip:text;background-clip:text;color:transparent}
.hero p.lead{color:var(--ash)}
.ticks span{color:#FFFFFF;background:rgba(255,255,255,.07);
  border-color:rgba(255,255,255,.16);box-shadow:none}
.ticks svg{color:var(--mint)}
@media (min-width: 900px){ .hero h1{font-size:54px} }

/* white cards on the dark canvas: the token sheet's "pearl inversion" */
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div >
  div[data-testid="stVerticalBlock"] > div[data-testid="element-container"] >
  div[data-testid="stMarkdown"] .panelmark),
div[data-testid="stVerticalBlock"]:not([data-testid="stVerticalBlockBorderWrapper"] *):has(
  > .element-container .panelmark){
  border:none!important;box-shadow:0 30px 80px rgba(6,6,40,.45)}
.feature,.step,.ag-card{border-color:transparent}
.feature .ic,.ag-card .ag-g{border-radius:12px}
.step .n{background:var(--iris-glow);border-radius:9999px}

.stApp:not(:has([role="tablist"])) .sect{color:var(--lilac)}
.stApp:not(:has([role="tablist"])) .sect::before{background:linear-gradient(var(--teal),var(--cyan))}
.stApp:not(:has([role="tablist"])) [data-testid="stCaptionContainer"],
.stApp:not(:has([role="tablist"])) [data-testid="stCaptionContainer"] *{color:var(--lilac)!important}
.stApp:not(:has([role="tablist"])) .ag-badge{background:rgba(255,255,255,.06);
  border-color:rgba(177,166,246,.35);color:var(--lilac)}
.stApp:not(:has([role="tablist"])) .ag-badge .ag-note,
.stApp:not(:has([role="tablist"])) .ag-badge .ag-role{color:var(--ash)}
.sitefoot{border-top-color:rgba(255,255,255,.12);color:var(--lilac)}
.sitefoot .mvname,.sitefoot b{color:#FFFFFF!important}
.sitefoot .mvname span{color:var(--teal)!important}

/* ---- inside the app ---------------------------------------------------------- */
.whoami{border-radius:var(--r-lg)}
.whoami .av{background:linear-gradient(135deg,var(--iris-glow),var(--iris-canvas));border-radius:9999px}
.whoami .count,.appbar .count,.rec .pill,.ag-badge,.ag-work,.ag-card:hover{border-color:var(--lilac-line)}
.prov.clinical{border-color:var(--lilac-line)}
.rec,.med,.empty,div[data-testid="stMetric"],div[data-testid="stFileUploader"]{border-radius:var(--r-lg)}
div[data-testid="stAlert"]{border-color:var(--lilac-line)}
div[data-testid="stAlert"] *{color:var(--iris-shadow)!important}

/* the emergency card: iris, with a cyan glow in the corner where the old one had white */
.idcard{background:
    radial-gradient(110% 90% at 100% 0%,rgba(0,177,255,.35),transparent 55%),
    linear-gradient(150deg,var(--iris-glow) 0%,var(--iris-shadow) 52%,var(--iris-canvas) 100%);
  box-shadow:0 18px 44px rgba(22,22,92,.32)}
.idcard::after{background:radial-gradient(120% 70% at 85% -10%,rgba(255,255,255,.14),transparent 60%)}
.idcard .brandline{color:var(--mint);opacity:1}
.idcard .cell{background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.14);border-radius:16px}

/* buttons are pills in the token sheet */
:is(.stButton,.stDownloadButton)>button,button[kind="primaryFormSubmit"],
button[kind="secondaryFormSubmit"]{border-radius:9999px!important}
:is(.stButton,.stDownloadButton)>button:hover{border-color:var(--lilac)}
:is(.stButton,.stDownloadButton)>button[kind="primary"],button[kind="primaryFormSubmit"]{
  background:var(--iris-glow)!important;border-color:var(--iris-glow)!important;box-shadow:none!important}
:is(.stButton,.stDownloadButton)>button[kind="primary"]:hover,button[kind="primaryFormSubmit"]:hover{
  background:var(--accent-bright)!important;border-color:var(--accent-bright)!important}
div[data-baseweb="input"],div[data-baseweb="select"]>div,div[data-baseweb="textarea"],
[data-testid="stTextInputRootElement"],[data-testid="stTextAreaRootElement"]{border-radius:16px!important}

/* the bar under the thumb, and on a laptop the rail: deep iris, labels in lilac */
[role="tablist"]{background:rgba(22,22,92,.96)!important;border-top:none!important;
  box-shadow:0 -4px 24px rgba(22,22,92,.25)!important}
[role="tablist"] [role="tab"] p{color:var(--lilac)!important}
[role="tablist"] [role="tab"]::before{background:var(--lilac)}
[role="tablist"] [role="tab"][aria-selected="true"] p{color:#FFFFFF!important}
[role="tablist"] [role="tab"][aria-selected="true"]::before{background:var(--mint)}
@media (min-width: 900px){
  [role="tablist"]{background:var(--iris-canvas)!important;border-right:none!important;box-shadow:none!important}
  [role="tablist"]::before{background:linear-gradient(135deg,var(--teal),var(--mint))}
  [role="tablist"]::after{color:#FFFFFF}
  [role="tablist"] [role="tab"]{border-radius:9999px}
  [role="tablist"] [role="tab"]:hover{background:rgba(255,255,255,.07)!important}
  [role="tablist"] [role="tab"][aria-selected="true"]{background:var(--iris-glow)!important}
  [role="tablist"] [role="tab"][aria-selected="true"]::before{background:#FFFFFF}
}
</style>
"""
