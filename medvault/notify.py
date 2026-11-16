#!/usr/bin/env python3
"""Notifications: a dose is due, a dose is still not marked, a box is running low, a
medicine is about to expire.

MedTimer (github.com/Futsch1/medTimer, MIT) notifies at each dose, reminds again when
nothing was done, and warns on low stock and on expiry. A web app cannot wake a phone, so
here the browser does it, while MedVault is open or installed and in the background; the
calendar file (schedule.calendar) stays the reminder that rings with MedVault closed, and
the screen says which is which.

**What is said is worked out here, in Python, and only shown by the browser.** plan()
is plain data, tested like the rest of the Scheduler; page() is a small script that asks
for permission once, shows what is already due, and times the rest. Each notification
carries a tag naming its medicine, its day and its time, and the browser remembers the
tags it has shown, so a rerun of the page never shows one twice. Nothing is sent to a
server: there is none in the loop.

**A lock screen is read by whoever picks the phone up.** private=True names no medicine
anywhere in a notification.
"""
import datetime
import json

import streamlit.components.v1 as components

import doses
import schedule

MORNING = datetime.time(9, 0)      # stock and expiry are raised once, at nine or straight away
HEIGHT = 58
PRIVATE_BODY = "Open MedVault to see which."


def _stamp(when):
    """A floating local time, "2026-11-03T20:00": the browser reads it on its own clock."""
    return when.strftime("%Y-%m-%dT%H:%M")


def _doses(rows, now, private):
    out, day = [], now.date().isoformat()
    grace = datetime.timedelta(minutes=doses.GRACE_MINUTES)
    for row in rows:
        if row["status"] not in ("upcoming", "due", "missed"):
            continue                              # taken or skipped: nothing left to say
        med, due = row["med"], datetime.datetime.combine(now.date(), datetime.time.fromisoformat(row["at"]))
        what = f"your {row['at']} medicine" if private else med["name"]
        tag = f"dose-{med['id']}-{day}-{row['at']}"
        if row["status"] == "upcoming":
            note = schedule.note(row["parsed"])
            body = PRIVATE_BODY if private else (med.get("dose") or "As prescribed") + (f" · {note}" if note else "")
            out.append({"tag": tag, "at": _stamp(due), "title": f"Time for {what}", "body": body})
        out.append({"tag": f"{tag}-check", "at": _stamp(max(due + grace, now)), "title": f"Not marked yet: {what}",
                    "body": f"Your {row['at']} dose. Did you take it? Tap Taken or Skip in MedVault."})
    return out


def _stock(med, now, morning, private):
    state, tag = doses.stock_state(med, now.date()), f"stock-{med['id']}-{now.date().isoformat()}"
    if state["level"] == "out":
        return {"tag": tag, "at": _stamp(now), "title": "A medicine has run out" if private else f"Out of {med['name']}",
                "body": PRIVATE_BODY if private else "Refill it before the next dose."}
    if state["level"] == "low":
        days = (state["runs_out"] - now.date()).days
        left = doses.count_text(state["left"], state["unit"])
        return {"tag": tag, "at": _stamp(morning),
                "title": "A medicine is running low" if private else f"Refill {med['name']} soon",
                "body": PRIVATE_BODY if private else f"{left} left, about {days} day{'' if days == 1 else 's'}."}
    return None


def _expiry(med, now, morning, private):
    state = doses.expiry_state(med, now.date())
    if not state:
        return None
    on = datetime.date.fromisoformat(med["expires"]).strftime("%-d %b %Y")
    if private:
        title = "A medicine has expired" if state == "expired" else "A medicine is about to expire"
    else:
        title = f"{med['name']} expired on {on}" if state == "expired" else f"{med['name']} expires {on}"
    return {"tag": f"expiry-{med['id']}-{now.date().isoformat()}", "at": _stamp(morning), "title": title,
            "body": PRIVATE_BODY if private else "Ask your pharmacist about a replacement."}


def plan(rows, meds, now, private=False):
    """Today's notifications, soonest first: doses.board() rows for the doses, and the
    active medicines for stock and expiry. `now` is the viewer's own wall clock."""
    morning = max(datetime.datetime.combine(now.date(), MORNING), now)
    boxes = [n for med in meds for n in (_stock(med, now, morning, private), _expiry(med, now, morning, private)) if n]
    return sorted(_doses(rows, now, private) + boxes, key=lambda n: n["at"])


# The page: a status line, a button the first time, and the script that shows and times
# each notification. It runs in Streamlit's component frame and works through the app's
# own window (window.parent), whose origin the permission and the stored tags belong to.
_PAGE = """<style>
body{margin:0;font:13px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#45457A}
.bar{display:flex;align-items:center;justify-content:space-between;gap:.6rem;padding:.5rem .8rem;
  border:1px solid #D8D8E3;border-radius:14px;background:#fff}
button{font:inherit;font-weight:600;color:#fff;background:#403CD5;border:0;border-radius:999px;
  padding:.45rem .95rem;cursor:pointer;white-space:nowrap}
button[hidden]{display:none}
</style>
<div class="bar"><span id="mv-status">Notifications</span><button id="mv-on" hidden>Turn on notifications</button></div>
<script>
(function () {
  var PLAN = __PLAN__;
  var APP = window.parent, KEY = "medvault-notified", DAY = 864e5;
  var N = APP.Notification || window.Notification;
  function seen() { try { return JSON.parse(APP.localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } }
  function remember(tag) {
    try {
      var all = seen(), now = Date.now();
      all[tag] = now;
      Object.keys(all).forEach(function (k) { if (now - all[k] > 2 * DAY) delete all[k]; });
      APP.localStorage.setItem(KEY, JSON.stringify(all));
    } catch (e) {}
  }
  // A registration whose worker is active: register() resolves while a new worker is
  // still installing, and showNotification() rejects until it is active. (ready is no
  // help: it waits for a worker controlling this page, and this one's scope is static/.)
  function active(reg) {
    if (!reg || reg.active) return Promise.resolve(reg || null);
    var w = reg.installing || reg.waiting;
    if (!w) return Promise.resolve(null);
    return new Promise(function (resolve) {
      w.addEventListener("statechange", function () {
        if (w.state === "activated") resolve(reg);
        if (w.state === "redundant") resolve(null);
      });
      setTimeout(function () { resolve(reg.active ? reg : null); }, 10000);
    });
  }
  function worker() {
    try {
      var sw = APP.navigator && APP.navigator.serviceWorker;
      if (!sw) return Promise.resolve(null);
      var scope = new URL("app/static/", APP.location.href).href;
      return sw.register(scope + "sw.js", {scope: scope}).then(active).catch(function () { return null; });
    } catch (e) { return Promise.resolve(null); }
  }
  // Remembered only once it has been shown: a notification that failed is tried again on
  // the next load, rather than marked as shown and never seen.
  function show(n) {
    if (seen()[n.tag]) return Promise.resolve();
    var icon = new URL("app/static/icon-192.png", APP.location.href).href;
    var options = {body: n.body, tag: n.tag, icon: icon, badge: icon, data: {url: APP.location.href}};
    return worker().then(function (reg) {
      if (reg && reg.showNotification) return reg.showNotification(n.title, options);
      throw new Error("no service worker");
    }).catch(function () {
      new N(n.title, options);              // throws where only a worker may show one
    }).then(function () { remember(n.tag); }, function () {});
  }
  function start() {
    var now = Date.now();
    PLAN.forEach(function (n) {
      var wait = new Date(n.at).getTime() - now;
      if (wait <= 0) show(n);
      else if (wait < DAY) setTimeout(function () { show(n); }, wait);
    });
  }
  var status = document.getElementById("mv-status"), button = document.getElementById("mv-on");
  function draw() {
    if (!N) {
      status.textContent = "This browser cannot show notifications here. The calendar file still reminds you.";
      return;
    }
    if (N.permission === "granted") {
      var now = Date.now(), left = PLAN.filter(function (n) { return new Date(n.at).getTime() > now; }).length;
      status.textContent = "Notifications on" + (left ? ": " + left + " more today, while MedVault is open." : ". Nothing more today.");
      button.hidden = true;
      start();
      return;
    }
    if (N.permission === "denied") {
      status.textContent = "Notifications are blocked for this site in your browser settings.";
      button.hidden = true;
      return;
    }
    status.textContent = "Get a notification at each dose, and when one is not marked.";
    button.hidden = false;
    button.onclick = function () { Promise.resolve(N.requestPermission()).then(draw); };
  }
  draw();
})();
</script>"""


def page(items):
    """The notification page for these items. The plan goes in as JSON with every <, > and
    & written as a \\u escape, so a medicine name read off a photograph can neither close
    the script it sits in nor open an HTML comment inside it ("<!--<script>" left the real
    </script> unable to close it, and every notification silently stopped)."""
    payload = (json.dumps(items, ensure_ascii=True)
               .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
    return _PAGE.replace("__PLAN__", payload)


def render(items):
    components.html(page(items), height=HEIGHT)
