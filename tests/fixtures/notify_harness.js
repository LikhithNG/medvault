// Runs notify.page()'s script against a stand-in browser, for tests/test_notify.py.
//   SW=none|installing|failing node tests/fixtures/notify_harness.js < page.html
//   -> {"shown": [...], "scheduled": n, "shown_after_reload": [...], "remembered": [...]}
// The clock is fixed at 12:00 on 3 November 2026 (run with TZ=UTC), notification permission
// is already granted, and the page is loaded twice against one localStorage, as a
// Streamlit rerun reloads it. SW picks the service worker:
//   none        no service worker at all, so the page's own Notification is used
//   installing  a worker that is still installing when register() resolves, and whose
//               showNotification rejects until it is active - as the spec requires
//   failing     every way of showing fails (Android Chrome has no Notification constructor)
const vm = require("vm");

const html = require("fs").readFileSync(0, "utf8");
const script = html.match(/<script>([\s\S]*)<\/script>/)[1];
const NOW = Date.UTC(2026, 10, 3, 12, 0);
const MODE = process.env.SW || "none";

class FixedDate extends Date {
  constructor(...args) { super(...(args.length ? args : [NOW])); }
  static now() { return NOW; }
}

const shown = [];
let scheduled = 0;
const store = {};
const storage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
function FakeNotification(title) {
  if (MODE === "failing") throw new TypeError("Illegal constructor");
  shown.push(title);
}
FakeNotification.permission = "granted";
FakeNotification.requestPermission = async () => "granted";

function serviceWorker() {
  if (MODE === "none") return undefined;
  if (MODE === "failing") {
    return { register: async () => ({ active: {}, showNotification: async () => { throw new TypeError("no"); } }) };
  }
  const listeners = [];
  const worker = { state: "installing", addEventListener: (_, fn) => listeners.push(fn) };
  const reg = {
    installing: worker, active: null,
    showNotification: async (title) => {
      if (!reg.active) throw new TypeError("No active registration.");
      shown.push(title);
    },
  };
  setImmediate(() => { worker.state = "activated"; reg.active = worker; reg.installing = null; listeners.forEach((fn) => fn()); });
  return { register: async () => reg };
}

const app = { localStorage: storage, Notification: FakeNotification, navigator: { serviceWorker: serviceWorker() },
              location: { href: "http://localhost:8503/" } };

async function load() {
  const element = () => ({ style: {}, textContent: "", onclick: null, hidden: false });
  const elements = {};
  const sandbox = {
    Date: FixedDate, URL, JSON, Promise, console, TypeError, Error,
    // A dose timer is hours away; a short timer (the page's wait for a worker) is not one.
    setTimeout: (fn, ms) => { if (ms > 60000) scheduled += 1; },
    document: { getElementById: (id) => (elements[id] = elements[id] || element()) },
    Notification: FakeNotification, navigator: {},
  };
  sandbox.window = { parent: app, top: app };
  vm.runInNewContext(script, sandbox);
  for (let i = 0; i < 10; i++) await new Promise((r) => setImmediate(r));
}

(async () => {
  await load();
  const first = [...shown];
  const firstScheduled = scheduled;
  await load();
  process.stdout.write(JSON.stringify({ shown: first, scheduled: firstScheduled, shown_after_reload: shown,
                                        remembered: Object.keys(JSON.parse(store["medvault-notified"] || "{}")) }));
})().catch((e) => { console.error(e); process.exit(1); });
