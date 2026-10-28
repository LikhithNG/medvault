#!/usr/bin/env python3
"""How the six agents look, and how they move.

Each agent has a small mark, and the mark's motion is its job: the Reader's scan line
moves down a page, the Checker draws a tick, the Advocate's letter lifts, the Companion's
dots wait for an answer, the Scheduler's clock hand turns, the Liaison passes something
between two people. Motion that does not say anything is decoration, and decoration on a
health screen is noise somebody has to read past.

The marks appear in three places: on the landing page, as a badge on everything an agent
produced (so a reader can always tell which agent made a figure, and whether a model was
involved), and as a working card while an agent is busy - which matters most for the two
that call a model, because those are the only waits long enough to wonder about.

**All of it stops for anybody who has asked their device to reduce motion.** That is not
a courtesy. Moving things trigger nausea and migraine for people with vestibular
disorders, and a medical records app is precisely where those people are. Every animation
lives inside one `prefers-reduced-motion: no-preference` block; tests/test_agentsui.py
fails if any escapes it. With motion off, every mark still reads as what it is.
"""
import agents

# One glyph per agent, 24x24, drawn in the stroke style of the navigation icons. The
# classed parts are the ones that move.
GLYPH = {
    "Reader": ('<path d="M7.2 3.5h6.8l4 4V19a1.5 1.5 0 0 1-1.5 1.5H7.5A1.5 1.5 0 0 1 6 19V5'
               'a1.5 1.5 0 0 1 1.2-1.5Z"/><path d="M14 3.5V8h4"/>'
               '<line class="ag-scan" x1="8.4" y1="10.5" x2="15.6" y2="10.5"/>'),
    "Checker": ('<circle cx="10.8" cy="10.8" r="6.3"/><path d="M15.4 15.4 20 20"/>'
                '<path class="ag-tick" d="M8.1 10.9l1.9 1.9 3.6-3.7"/>'),
    "Advocate": ('<g class="ag-lift"><rect x="3.5" y="6.5" width="17" height="11.5" rx="2"/>'
                 '<path d="M4.2 7.6 12 13.2l7.8-5.6"/></g>'),
    "Companion": ('<path d="M12 4.2c-4.4 0-8 2.9-8 6.5 0 2 1.1 3.8 2.8 5V19l3.1-1.9c.7.1 1.4.2'
                  ' 2.1.2 4.4 0 8-2.9 8-6.6S16.4 4.2 12 4.2Z"/>'
                  '<circle class="fill ag-dot d1" cx="8.6" cy="10.8" r="1"/>'
                  '<circle class="fill ag-dot d2" cx="12" cy="10.8" r="1"/>'
                  '<circle class="fill ag-dot d3" cx="15.4" cy="10.8" r="1"/>'),
    "Scheduler": ('<circle cx="12" cy="12" r="8.3"/>'
                  '<line class="ag-hand" x1="12" y1="12" x2="12" y2="6.8"/>'
                  '<line x1="12" y1="12" x2="15.2" y2="13.6"/>'
                  '<circle class="fill" cx="12" cy="12" r="1"/>'),
    "Liaison": ('<circle cx="6" cy="12" r="2.6"/><circle cx="18" cy="12" r="2.6"/>'
                '<line x1="8.6" y1="12" x2="15.4" y2="12" stroke-dasharray="1.6 1.8"/>'
                '<circle class="fill ag-pulse" cx="9" cy="12" r="1.3"/>'),
}

# What each one does, in a sentence somebody holding a bill would understand. The longer,
# exact versions live in agents.py.
SHORT = {
    "Reader": "Reads a photo or PDF and turns it into a record.",
    "Checker": "Prices every line against what the hospital published.",
    "Advocate": "Writes the letter, ranked by the money at stake.",
    "Companion": "Answers questions about your own records.",
    "Scheduler": "Turns prescriptions into reminders your phone rings.",
    "Liaison": "Shows your doctor what your records say is outstanding.",
}

CSS = """
<style>
.ag-g svg{fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;
  stroke-linejoin:round;display:block}
.ag-g svg .fill{fill:currentColor;stroke:none}

/* the badge on anything an agent produced */
.ag-badge{display:inline-flex;align-items:center;gap:.42rem;font-size:10.5px;
  font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--accent);
  background:var(--accent-soft);border:1px solid #D6E6FD;border-radius:999px;
  padding:.2rem .62rem .2rem .22rem;margin:-.2rem 0 .65rem}
.ag-badge .ag-g{width:21px;height:21px;border-radius:7px;background:var(--card);
  display:flex;align-items:center;justify-content:center;color:var(--accent)}
.ag-badge .ag-g svg{width:15px;height:15px}
.ag-badge .ag-role{color:var(--faint);font-weight:600}
.ag-badge .ag-live{width:6px;height:6px;border-radius:50%;background:var(--ok);
  display:inline-block}
.ag-badge.model .ag-live{background:var(--warn)}

/* the landing-page roster */
.ag-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.6rem}
.ag-card{background:var(--card);border:1px solid var(--line);border-radius:var(--r-lg);
  padding:.95rem .9rem 1rem;box-shadow:var(--sh-sm)}
.ag-card .ag-g{width:44px;height:44px;border-radius:13px;background:var(--accent-soft);
  color:var(--accent);display:flex;align-items:center;justify-content:center;
  margin-bottom:.6rem}
.ag-card .ag-g svg{width:27px;height:27px}
.ag-card .ag-n{font-size:15px;font-weight:800;color:var(--ink);letter-spacing:-.02em}
.ag-card .ag-r{font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  color:var(--faint);margin:.1rem 0 .4rem}
.ag-card p{font-size:13px;line-height:1.5;color:var(--soft);margin:0}
.ag-card .ag-kind{display:inline-block;margin-top:.55rem;font-size:10.5px;font-weight:700;
  padding:.14rem .45rem;border-radius:999px;background:var(--ok-soft);color:var(--ok);
  border:1px solid #BCE5CF}
.ag-card .ag-kind.model{background:var(--warn-soft);color:var(--warn);border-color:#F7E0B5}

/* an agent at work */
.ag-work{position:relative;overflow:hidden;display:flex;align-items:center;gap:.85rem;
  background:var(--card);border:1px solid #D6E6FD;border-radius:var(--r);
  padding:.85rem .95rem .95rem;box-shadow:var(--sh-md);margin:.4rem 0 .8rem}
.ag-work .ag-g{flex:0 0 auto;width:46px;height:46px;border-radius:13px;
  background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;
  justify-content:center}
.ag-work .ag-g svg{width:28px;height:28px}
.ag-work .ag-wt{font-size:14.5px;font-weight:700;color:var(--ink);letter-spacing:-.01em}
.ag-work .ag-ws{font-size:12.5px;color:var(--soft);margin-top:.15rem}
.ag-work .ag-bar{position:absolute;left:0;right:0;bottom:0;height:3px;
  background:var(--accent-soft)}
.ag-work .ag-bar i{position:absolute;top:0;bottom:0;width:34%;
  background:linear-gradient(90deg,transparent,var(--accent),transparent)}

@media (min-width: 900px){ .ag-grid{grid-template-columns:repeat(3,minmax(0,1fr))} }

/* ---- motion: every animation lives in here, and only in here -------------- */
@media (prefers-reduced-motion: no-preference){
  .ag-scan{animation:ag-scan 2.4s ease-in-out infinite}
  .ag-tick{stroke-dasharray:14;stroke-dashoffset:14;animation:ag-draw 2.8s ease-in-out infinite}
  .ag-lift{animation:ag-lift 2.6s ease-in-out infinite}
  .ag-dot{animation:ag-bounce 1.3s ease-in-out infinite}
  .ag-dot.d2{animation-delay:.16s} .ag-dot.d3{animation-delay:.32s}
  .ag-hand{transform-box:view-box;transform-origin:12px 12px;
    animation:ag-spin 7s linear infinite}
  .ag-pulse{animation:ag-travel 2.2s ease-in-out infinite}
  .ag-live{animation:ag-live 2.4s ease-in-out infinite}
  .ag-work .ag-bar i{animation:ag-sweep 1.5s ease-in-out infinite}
  .ag-in{animation:ag-in .42s cubic-bezier(.2,.7,.3,1) both;
    animation-delay:calc(var(--i, 0) * 70ms)}
  .ag-next{animation:ag-glow 2.2s ease-in-out 3}

  @keyframes ag-scan{0%,100%{transform:translateY(0);opacity:.35}
    50%{transform:translateY(7px);opacity:1}}
  @keyframes ag-draw{0%{stroke-dashoffset:14}45%,80%{stroke-dashoffset:0}
    100%{stroke-dashoffset:-14}}
  @keyframes ag-lift{0%,100%{transform:translateY(0)}50%{transform:translateY(-1.6px)}}
  @keyframes ag-bounce{0%,60%,100%{transform:translateY(0);opacity:.45}
    30%{transform:translateY(-2.2px);opacity:1}}
  @keyframes ag-spin{to{transform:rotate(360deg)}}
  @keyframes ag-travel{0%{transform:translateX(0);opacity:0}15%{opacity:1}
    85%{opacity:1}100%{transform:translateX(6px);opacity:0}}
  @keyframes ag-live{0%,100%{box-shadow:0 0 0 0 rgba(6,118,71,.45)}
    60%{box-shadow:0 0 0 5px rgba(6,118,71,0)}}
  @keyframes ag-sweep{0%{left:-34%}100%{left:100%}}
  @keyframes ag-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
  @keyframes ag-glow{0%,100%{box-shadow:var(--sh-sm)}
    50%{box-shadow:0 0 0 4px rgba(6,118,71,.16),var(--sh-md)}}
}
</style>
"""


def _glyph(name):
    return (f'<span class="ag-g"><svg viewBox="0 0 24 24" aria-hidden="true">'
            f'{GLYPH[name]}</svg></span>')


def badge(name):
    """Which agent produced what follows, and whether a model was involved.

    The live dot is green for a deterministic agent and amber for one that calls a
    model - the same distinction the README's agent table draws, made visible where the
    output is, rather than in a document nobody reads before believing a figure.
    """
    agent = agents.BY_NAME[name]
    model = agent["generative"]
    return (f'<div class="ag-badge{" model" if model else ""}" '
            f'title="{"Uses a model" if model else "No model involved"}">'
            f'{_glyph(name)}{name} <span class="ag-role">· {agent["madison"]}</span>'
            f'<span class="ag-live"></span></div>')


def working(name, doing, step=""):
    """The card shown while an agent is busy. Replaced by its result when it finishes."""
    return (f'<div class="ag-work" role="status" aria-live="polite">{_glyph(name)}'
            f'<div><div class="ag-wt">{name} · {doing}</div>'
            + (f'<div class="ag-ws">{step}</div>' if step else "")
            + '</div><div class="ag-bar"><i></i></div></div>')


def roster():
    """All six, for the landing page."""
    cards = []
    for i, agent in enumerate(agents.AGENTS):
        name = agent["name"]
        model = agent["generative"]
        cards.append(
            f'<div class="ag-card ag-in" style="--i:{i}">{_glyph(name)}'
            f'<div class="ag-n">{name}</div><div class="ag-r">Madison {agent["madison"]}</div>'
            f'<p>{SHORT[name]}</p>'
            f'<span class="ag-kind{" model" if model else ""}">'
            f'{"Uses a model" if model else "No model — arithmetic"}</span></div>')
    return f'<div class="ag-grid">{"".join(cards)}</div>'


def arrive(i):
    """Inline style that staggers a card's entrance by its position in a list."""
    return f' style="--i:{min(i, 8)}"'
