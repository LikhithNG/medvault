#!/usr/bin/env python3
"""Make the page installable to a phone's home screen.

A web app becomes an app when the browser finds a manifest and the right meta tags in the
document head. Streamlit gives no way to put them there: st.markdown sanitises <link> and
<meta> out, and set_page_config only reaches the favicon.

The one route that works is a components.v1.html block. It renders inside an iframe, and
from there it can reach up into the document Streamlit controls and write into its head.
The iframe itself is given zero height so nothing appears on screen.

**window.parent is not far enough, and that cost a working install.** Locally the app is
the top-level page, so window.parent.document was it. Deployed to Streamlit Community
Cloud the app is itself inside an iframe on a wrapper page, so window.parent reached only
the app document - and a browser installs from the TOP document, which still carried
Streamlit's own manifest, Streamlit's icon and a white theme colour. Every tag was
present, in a document nobody installs from. Checked on the deployment rather than
assumed: the inner frame had theme-color #0F6FDE and the outer had #FFFFFF.

So this writes into window.top when it can reach it, and falls back to window.parent when
it cannot. The hrefs are resolved to absolute URLs against the APP's location first,
because "app/static/manifest.json" relative to the wrapper is a path the wrapper answers
with HTML, while relative to the app it is the file.

Serving the files relies on [server] enableStaticServing in config.toml, which publishes
static/ at <app>/app/static/ - on Cloud that is under the app's own path, not the host
root.
"""
import streamlit as st
import streamlit.components.v1 as components

HEAD = [
    ('link', {'rel': 'manifest', 'href': 'app/static/manifest.json'}),
    ('link', {'rel': 'apple-touch-icon', 'href': 'app/static/icon-180.png'}),
    ('meta', {'name': 'apple-mobile-web-app-capable', 'content': 'yes'}),
    ('meta', {'name': 'mobile-web-app-capable', 'content': 'yes'}),
    # black-translucent lets the page paint under the status bar, which is what stops an
    # installed app looking like a web page with a white strip above it.
    ('meta', {'name': 'apple-mobile-web-app-status-bar-style', 'content': 'black-translucent'}),
    ('meta', {'name': 'apple-mobile-web-app-title', 'content': 'MedVault'}),
    ('meta', {'name': 'theme-color', 'content': '#16165C'}),
    ('meta', {'name': 'viewport',
              'content': 'width=device-width, initial-scale=1, viewport-fit=cover'}),
]


# Attributes holding a URL, which has to be made absolute before it is written into a
# document that may sit at a different path from the app.
URL_ATTRS = ('href',)


def _js():
    out = ["""
var APP = window.parent;
var base = APP.location.href;
// Every document the tags should land in: the app's own, and - when the app is framed,
// which is what Streamlit Cloud does - the top one, because that is the document a
// browser reads when somebody installs the page.
var docs = [APP.document];
try { if (window.top && window.top !== APP && window.top.document) docs.push(window.top.document); }
catch (e) { /* cross-origin top: nothing to do but leave the app document correct */ }
function put(tag, attrs, sel) {
  docs.forEach(function (d) {
    var old = d.querySelector(sel);
    if (old) old.remove();                       // replace: a second tag lower down loses
    var e = d.createElement(tag);
    Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    d.head.appendChild(e);
  });
}
"""]
    for tag, attrs in HEAD:
        key = 'rel' if tag == 'link' else 'name'
        sel = f"{tag}[{key}='{attrs[key]}']"
        resolved = dict(attrs)
        absolute = [k for k in resolved if k in URL_ATTRS]
        pairs = ",".join(f"{k!r}:{v!r}" for k, v in resolved.items())
        fix = "".join(
            f"a[{k!r}] = new URL(a[{k!r}], base).href;" for k in absolute)
        out.append(f"(function(){{var a={{{pairs}}};{fix}put({tag!r},a,{sel!r});}})();")
    return "\n".join(out)


def install():
    """Inject the manifest and meta tags. Call once, near the top of the app."""
    if st.session_state.get("_pwa_done"):
        return
    components.html(f"<script>{_js()}</script>", height=0, width=0)
    st.session_state["_pwa_done"] = True
