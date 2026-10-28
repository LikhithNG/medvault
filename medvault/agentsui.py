#!/usr/bin/env python3
"""How the six agents look, and how they move.

Each agent has a small mark, and the mark's motion is its job: the Reader's scan line
moves down a page, the Checker draws a tick, the Advocate's letter lifts, the Companion's
dots wait for an answer, the Scheduler's clock hand turns, the Liaison passes something
between two people and back. Motion that does not say anything is decoration, and
decoration on a health screen is noise somebody has to read past.

**A mark moves when its agent is used, and only then.** The first version looped every
mark forever, which on a results screen says "still working" about an agent that finished
seconds ago - a small lie, repeated on every badge. So there are three states:

  * at rest - the mark sits still. Nothing is happening, and it does not pretend to be.
  * working - the motion loops, for as long as the agent is actually busy (`ag-on`).
  * just finished - the motion plays once, as the result arrives, then stops (`ag-once`).
    Streamlit only redraws an element whose content changed, so "once" means once per
    time the agent produced something new - not once per click anywhere on the page.

The relay is the multi-agent version: the Bill screen hands a bill from the Reader to the
Checker to the Advocate, and the relay shows each one start, work and finish, with how
long it actually took. No step is padded to look busy. An agent that answers in two
milliseconds is shown taking two milliseconds - that is the point of "no model".

**All of it stops for anybody who has asked their device to reduce motion.** That is not
a courtesy. Moving things trigger nausea and migraine for people with vestibular
disorders, and a medical records app is precisely where those people are. Every animation
lives inside one `prefers-reduced-motion: no-preference` block; tests/test_agentsui.py
fails if any escapes it. With motion off, every state still reads - by colour, by the
tick on a finished step, and by the words beside it.
"""
import html

import agents

# One glyph per agent, 24x24, drawn in the stroke style of the navigation icons. The parts
# classed ag-m are the ones that move; the second class says how.
GLYPH = {
    "Reader": ('<path d="M7.2 3.5h6.8l4 4V19a1.5 1.5 0 0 1-1.5 1.5H7.5A1.5 1.5 0 0 1 6 19V5'
               'a1.5 1.5 0 0 1 1.2-1.5Z"/><path d="M14 3.5V8h4"/>'
               '<line class="ag-m ag-scan" x1="8.4" y1="10.5" x2="15.6" y2="10.5"/>'),
    "Checker": ('<circle cx="10.8" cy="10.8" r="6.3"/><path d="M15.4 15.4 20 20"/>'
                '<path class="ag-m ag-tick" d="M8.1 10.9l1.9 1.9 3.6-3.7"/>'),
    "Advocate": ('<g class="ag-m ag-lift"><rect x="3.5" y="6.5" width="17" height="11.5" rx="2"/>'
                 '<path d="M4.2 7.6 12 13.2l7.8-5.6"/></g>'),
    "Companion": ('<path d="M12 4.2c-4.4 0-8 2.9-8 6.5 0 2 1.1 3.8 2.8 5V19l3.1-1.9c.7.1 1.4.2'
                  ' 2.1.2 4.4 0 8-2.9 8-6.6S16.4 4.2 12 4.2Z"/>'
                  '<circle class="fill ag-m ag-dot d1" cx="8.6" cy="10.8" r="1"/>'
                  '<circle class="fill ag-m ag-dot d2" cx="12" cy="10.8" r="1"/>'
                  '<circle class="fill ag-m ag-dot d3" cx="15.4" cy="10.8" r="1"/>'),
    "Scheduler": ('<circle cx="12" cy="12" r="8.3"/>'
                  '<line class="ag-m ag-hand" x1="12" y1="12" x2="12" y2="6.8"/>'
                  '<line x1="12" y1="12" x2="15.2" y2="13.6"/>'
                  '<circle class="fill" cx="12" cy="12" r="1"/>'),
    "Liaison": ('<circle cx="6" cy="12" r="2.6"/><circle cx="18" cy="12" r="2.6"/>'
                '<line x1="8.6" y1="12" x2="15.4" y2="12" stroke-dasharray="1.6 1.8"/>'
                '<circle class="fill ag-m ag-pulse" cx="9" cy="12" r="1.3"/>'),
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

# The states a step in a relay can be in. "fail" is its own state rather than "skip",
# because an agent that could not do its job and one that was not needed are different
# things to the person waiting on it.
STATES = ("wait", "work", "done", "skip", "fail")
_RESTING = {"wait": "Next", "work": "Working…", "done": "Done", "skip": "Not needed",
            "fail": "Could not finish"}

# How far down a list the entrance keeps staggering. Past this everything left arrives
# together, so a long list never takes seconds to finish appearing.
STAGGER = 8

_TICK = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 12.5l4 4 8-9"/></svg>')

CSS = """
<style>
__STAGGER__
.ag-g svg{fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;
  stroke-linejoin:round;display:block;overflow:visible}
.ag-g svg .fill{fill:currentColor;stroke:none}

/* the badge on anything an agent produced */
.ag-badge{display:inline-flex;align-items:center;gap:.42rem;font-size:10.5px;
  font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--accent);
  background:var(--accent-soft);border:1px solid #D6E6FD;border-radius:999px;
  padding:.2rem .62rem .2rem .22rem;margin:-.2rem 0 .65rem;white-space:nowrap}
.ag-badge .ag-g{width:21px;height:21px;border-radius:7px;background:var(--card);
  display:flex;align-items:center;justify-content:center;color:var(--accent)}
.ag-badge .ag-g svg{width:15px;height:15px}
.ag-badge .ag-role{color:var(--faint);font-weight:600}
.ag-badge .ag-note{color:var(--soft);font-weight:600;text-transform:none;letter-spacing:0}
.ag-badge .ag-live{width:6px;height:6px;border-radius:50%;background:var(--ok);
  display:inline-block;flex:0 0 auto}
.ag-badge.model .ag-live{background:var(--warn)}

/* a section heading and the agent behind it, on one line */
.ag-head{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;
  gap:.4rem .7rem;margin:1.4rem 0 .65rem}
.ag-head>.sect{margin:0}
.ag-head>.ag-badge{margin:0}

/* the landing-page roster */
.ag-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.6rem}
.ag-card{background:var(--card);border:1px solid var(--line);border-radius:var(--r-lg);
  padding:.95rem .9rem 1rem;box-shadow:var(--sh-sm);
  transition:box-shadow .18s ease,border-color .18s ease}
.ag-card:hover{box-shadow:var(--sh-md);border-color:#D6E6FD}
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

/* one agent at work */
.ag-work{position:relative;overflow:hidden;display:flex;align-items:center;gap:.85rem;
  background:var(--card);border:1px solid #D6E6FD;border-radius:var(--r);
  padding:.85rem .95rem .95rem;box-shadow:var(--sh-md);margin:.4rem 0 .8rem}
.ag-work .ag-g{flex:0 0 auto;width:46px;height:46px;border-radius:13px;
  background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;
  justify-content:center}
.ag-work .ag-g svg{width:28px;height:28px}
.ag-work .ag-wt{font-size:14.5px;font-weight:700;color:var(--ink);letter-spacing:-.01em}
.ag-work .ag-ws{font-size:12.5px;color:var(--soft);margin-top:.15rem}
.ag-bar{position:absolute;left:0;right:0;bottom:0;height:3px;background:var(--accent-soft)}
.ag-bar i{position:absolute;top:0;bottom:0;left:0;width:34%;
  background:linear-gradient(90deg,transparent,var(--accent),transparent)}

/* several agents handing one job along */
.ag-relay{position:relative;overflow:hidden;background:var(--card);
  border:1px solid var(--line);border-radius:var(--r-lg);padding:.9rem .9rem .8rem;
  box-shadow:var(--sh-sm);margin:.3rem 0 .8rem;transition:border-color .3s ease}
.ag-relay.busy{border-color:#D6E6FD;box-shadow:var(--sh-md)}
.ag-steps{display:flex;align-items:flex-start}
.ag-step{flex:0 0 auto;width:92px;display:flex;flex-direction:column;align-items:center;
  text-align:center}
.ag-mk{position:relative}
.ag-step .ag-g{width:42px;height:42px;border-radius:13px;background:var(--line-soft);
  color:var(--faint);display:flex;align-items:center;justify-content:center;
  transition:background .3s ease,color .3s ease,box-shadow .3s ease}
.ag-step .ag-g svg{width:25px;height:25px}
.ag-step.work .ag-g,.ag-step.done .ag-g{background:var(--accent-soft);color:var(--accent)}
.ag-step.work .ag-g{box-shadow:0 0 0 4px rgba(15,111,222,.12)}
.ag-step.fail .ag-g{background:var(--danger-soft);color:var(--danger)}
.ag-step.skip{opacity:.55}
.ag-sn{font-size:12.5px;font-weight:800;color:var(--ink);margin-top:.42rem;
  letter-spacing:-.01em}
.ag-step.wait .ag-sn{color:var(--soft)}
.ag-ss{font-size:11px;color:var(--faint);margin-top:.08rem;line-height:1.3}
.ag-step.work .ag-ss{color:var(--accent);font-weight:700}
.ag-step.done .ag-ss{color:var(--ok);font-weight:700}
.ag-step.fail .ag-ss{color:var(--danger);font-weight:700}
.ag-ok{position:absolute;right:-5px;bottom:-5px;width:18px;height:18px;border-radius:50%;
  background:var(--ok);display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 0 2px var(--card)}
.ag-ok svg{width:11px;height:11px;fill:none;stroke:#fff;stroke-width:3;
  stroke-linecap:round;stroke-linejoin:round}
.ag-link{flex:1 1 auto;min-width:10px;height:2px;margin:20px -10px 0;border-radius:2px;
  background:var(--line);position:relative;overflow:hidden}
.ag-link.on{background:var(--accent)}
.ag-link.go{background:var(--accent-soft)}
.ag-link i{position:absolute;top:0;bottom:0;left:0;width:45%;display:none;
  background:linear-gradient(90deg,transparent,var(--accent),transparent)}
.ag-link.go i{display:block}
.ag-now{font-size:12.5px;color:var(--soft);line-height:1.5;margin-top:.75rem;
  padding-top:.6rem;border-top:1px dashed var(--line)}
.ag-now b{color:var(--ink)}

/* the line under an answer that says who answered, and how fast */
.ag-stamp{display:flex;align-items:center;gap:.4rem;font-size:11.5px;color:var(--faint);
  margin-top:.65rem}
.ag-stamp .ag-g{width:18px;height:18px;color:var(--accent)}
.ag-stamp .ag-g svg{width:16px;height:16px}
.ag-stamp b{color:var(--soft);font-weight:700}

@media (min-width: 900px){ .ag-grid{grid-template-columns:repeat(3,minmax(0,1fr))} }
@media (max-width: 420px){ .ag-step{width:78px} .ag-ss{font-size:10.5px} }

/* ---- motion: every animation lives in here, and only in here -------------- */
@media (prefers-reduced-motion: no-preference){
  /* what each moving part does. The state decides how many times. */
  .ag-scan{--ag-a:ag-scan 1.5s ease-in-out}
  .ag-tick{--ag-a:ag-draw 1.5s ease-out}
  .ag-lift{--ag-a:ag-lift 1.3s ease-in-out}
  .ag-dot{--ag-a:ag-bounce 1.2s ease-in-out}
  .ag-dot.d2{--ag-off:.16s} .ag-dot.d3{--ag-off:.32s}
  .ag-hand{--ag-a:ag-spin 1.8s cubic-bezier(.45,.05,.35,1);
    transform-box:view-box;transform-origin:12px 12px}
  .ag-pulse{--ag-a:ag-travel 1.6s ease-in-out}

  /* working: loops for as long as the agent is busy */
  .ag-on .ag-m{animation:var(--ag-a) infinite;animation-delay:var(--ag-off, 0s)}
  /* a visitor pointing at a roster card is asking to see it work - but only with a real
     pointer: on a phone :hover sticks after a tap and the mark would loop until the next */
  @media (hover: hover){
    .ag-card:hover .ag-m{animation:var(--ag-a) infinite;animation-delay:var(--ag-off, 0s)}
  }
  /* just finished, or just arrived: once, then still */
  .ag-once .ag-m{animation:var(--ag-a) 1 both;
    animation-delay:calc(var(--ag-at, .15s) + var(--ag-off, 0s))}
  .ag-on .ag-tick,.ag-once .ag-tick,.ag-card:hover .ag-tick{stroke-dasharray:14}
  /* the roster takes turns: each agent shows its job once as the page arrives */
  .ag-card.ag-once{--ag-at:calc(var(--i, 0) * 180ms + .35s)}

  .ag-bar i{animation:ag-sweep 1.5s ease-in-out infinite}
  .ag-link.go i{animation:ag-sweep 1.1s ease-in-out infinite}
  .ag-step.done.ag-once .ag-ok{animation:ag-pop .45s cubic-bezier(.2,.9,.3,1.3) both;
    animation-delay:calc(var(--ag-at, .15s) + .9s)}
  .ag-in{animation:ag-in .42s cubic-bezier(.2,.7,.3,1) both;
    animation-delay:calc(var(--i, 0) * 70ms)}
  .ag-next{animation:ag-glow 2.2s ease-in-out 3}

  @keyframes ag-scan{0%,100%{transform:none}50%{transform:translateY(7px)}}
  @keyframes ag-draw{0%{stroke-dashoffset:14}60%,100%{stroke-dashoffset:0}}
  @keyframes ag-lift{0%,100%{transform:none}45%{transform:translateY(-2px)}}
  @keyframes ag-bounce{0%,60%,100%{transform:none}30%{transform:translateY(-2.4px)}}
  @keyframes ag-spin{to{transform:rotate(360deg)}}
  @keyframes ag-travel{0%,100%{transform:none}50%{transform:translateX(6px)}}
  @keyframes ag-sweep{0%{transform:translateX(-100%)}100%{transform:translateX(300%)}}
  @keyframes ag-pop{0%{transform:scale(0)}100%{transform:scale(1)}}
  @keyframes ag-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
  @keyframes ag-glow{0%,100%{box-shadow:var(--sh-sm)}
    50%{box-shadow:0 0 0 4px rgba(6,118,71,.16),var(--sh-md)}}
}
</style>
"""


# Position in a list, and turn in a relay, as classes - see arrive() for why not styles.
CSS = CSS.replace("__STAGGER__", "".join(
    f".ag-i{n}{{--i:{n}}}.ag-t{n}{{--ag-at:{0.15 + 0.4 * n:.2f}s}}"
    for n in range(1, STAGGER + 1)))


def _glyph(name):
    return (f'<span class="ag-g"><svg viewBox="0 0 24 24" aria-hidden="true">'
            f'{GLYPH[name]}</svg></span>')


def took(seconds):
    """How long an agent took, in the unit a person reads at a glance."""
    if seconds < 0.001:
        return "<1 ms"
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    return f"{seconds:.1f} s"


def badge(name, note=""):
    """Which agent produced what follows, and whether a model was involved.

    The dot is green for a deterministic agent and amber for one that calls a model - the
    same distinction the README's agent table draws, made visible where the output is,
    rather than in a document nobody reads before believing a figure. The mark plays its
    motion once as the badge arrives: this agent just did this.
    """
    agent = agents.BY_NAME[name]
    model = agent["generative"]
    extra = f'<span class="ag-note">· {html.escape(note)}</span>' if note else ""
    return (f'<div class="ag-badge ag-once{" model" if model else ""}" '
            f'title="{"Uses a model" if model else "No model involved"}">'
            f'{_glyph(name)}{name} <span class="ag-role">· {agent["madison"]}</span>'
            f'{extra}<span class="ag-live"></span></div>')


def heading(section_html, name, note=""):
    """A section heading with the agent behind it beside it, rather than under it."""
    return f'<div class="ag-head">{section_html}{badge(name, note)}</div>'


def working(name, doing, step=""):
    """The card shown while one agent is busy. Replaced by its result when it finishes."""
    return (f'<div class="ag-work ag-on" role="status" aria-live="polite">{_glyph(name)}'
            f'<div><div class="ag-wt">{name} · {html.escape(doing)}</div>'
            + (f'<div class="ag-ws">{html.escape(step)}</div>' if step else "")
            + '</div><div class="ag-bar"><i></i></div></div>')


def stamp(name, note):
    """The line under an answer: which agent gave it, and how long it took."""
    return (f'<div class="ag-stamp ag-once">{_glyph(name)}<span><b>{name}</b> · '
            f'{html.escape(note)}</span></div>')


# ---- the relay ------------------------------------------------------------------

def step(name, state="wait", note="", fresh=False, turn=0):
    if state not in STATES:
        raise ValueError(f"unknown relay state {state!r}")
    return {"name": name, "state": state, "note": note, "fresh": fresh, "turn": turn}


def advance(steps, name, state, note=""):
    """The relay with one agent moved on. Returns a new list; the old one is untouched.

    Only the agent that just moved is marked fresh. Streamlit redraws the whole relay on
    every update, so without this the Reader's finishing tick would replay each time the
    Checker or the Advocate moved - three "done"s for one piece of work.
    """
    if name not in {s["name"] for s in steps}:
        raise KeyError(f"{name} is not in this relay")
    return [step(name, state, note, fresh=True) if s["name"] == name
            else step(s["name"], s["state"], s["note"]) for s in steps]


def finale(steps, names):
    """The relay at rest once the run is over.

    The agents in `names` finished too fast for the frame that showed them finishing to
    be seen - two milliseconds is not a frame - so they show their work once more here, in
    the order they did it and a beat apart, which is what makes a hand-off read as one.
    Every other step is drawn still.
    """
    out, turn = [], 0
    for s in steps:
        fresh = s["name"] in names and s["state"] == "done"
        out.append(step(s["name"], s["state"], s["note"], fresh=fresh, turn=turn))
        turn += fresh
    return out


def _relay_step(s):
    fresh = s["state"] == "done" and s.get("fresh")
    motion = {"work": " ag-on", "done": " ag-once" if fresh else ""}.get(s["state"], "")
    at = f' ag-t{min(s.get("turn", 0), STAGGER)}' if fresh else ""
    tick = f'<span class="ag-ok">{_TICK}</span>' if s["state"] == "done" else ""
    note = s["note"] or _RESTING[s["state"]]
    return (f'<div class="ag-step {s["state"]}{motion}{at}"><div class="ag-mk">'
            f'{_glyph(s["name"])}{tick}</div><div class="ag-sn">{s["name"]}</div>'
            f'<div class="ag-ss">{html.escape(note)}</div></div>')


def _link(before, after):
    """The line between two steps: lit once the job has passed along it."""
    passed = ("done", "skip", "fail")
    if after["state"] == "work":
        return '<div class="ag-link go"><i></i></div>'
    if before["state"] in passed and after["state"] in passed:
        return '<div class="ag-link on"></div>'
    return '<div class="ag-link"></div>'


def relay(steps, now=""):
    """A job handed from agent to agent, with where it has got to.

    `now` is one plain sentence under the steps: what the working agent is doing, or what
    the whole run found once it is over. It is escaped, because part of it can come off a
    bill a model read.
    """
    busy = any(s["state"] == "work" for s in steps)
    parts = []
    for i, s in enumerate(steps):
        if i:
            parts.append(_link(steps[i - 1], s))
        parts.append(_relay_step(s))
    return (f'<div class="ag-relay{" busy" if busy else ""}" role="status" '
            f'aria-live="polite"><div class="ag-steps">{"".join(parts)}</div>'
            + (f'<div class="ag-now">{html.escape(now)}</div>' if now else "")
            + ('<div class="ag-bar"><i></i></div>' if busy else "") + '</div>')


def roster():
    """All six, for the landing page. Each shows its job once, in turn, then rests;
    hovering a card shows it again."""
    cards = []
    for i, agent in enumerate(agents.AGENTS):
        name = agent["name"]
        model = agent["generative"]
        cards.append(
            f'<div class="ag-card ag-once ag-in {arrive(i)}">{_glyph(name)}'
            f'<div class="ag-n">{name}</div><div class="ag-r">Madison {agent["madison"]}</div>'
            f'<p>{SHORT[name]}</p>'
            f'<span class="ag-kind{" model" if model else ""}">'
            f'{"Uses a model" if model else "No model — arithmetic"}</span></div>')
    return f'<div class="ag-grid">{"".join(cards)}</div>'


def arrive(i):
    """The class that staggers a card's entrance by its position in a list.

    A class, not an inline style that sets --i. Streamlit's markdown renderer drops custom
    properties from inline styles without a word, so the first version of this staggered
    nothing - every card arrived at once - and the markup looked right to anyone reading
    it. tests/test_agentsui.py now fails on an inline custom property anywhere.
    """
    return f"ag-i{min(i, STAGGER)}"
