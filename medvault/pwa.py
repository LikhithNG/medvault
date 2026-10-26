#!/usr/bin/env python3
"""Make the page installable to a phone's home screen.

A web app becomes an app when the browser finds a manifest and the right meta tags in the
document head. Streamlit gives no way to put them there: st.markdown sanitises <link> and
<meta> out, and set_page_config only reaches the favicon.

The one route that works is a components.v1.html block. It renders inside an iframe, and
from there window.parent.document is the real page - so a few lines of script injected once
can write into the head Streamlit controls. The iframe itself is given zero height so
nothing appears on screen.

Serving the files relies on [server] enableStaticServing in config.toml, which publishes
static/ at /app/static/.
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
    ('meta', {'name': 'theme-color', 'content': '#0F6FDE'}),
    ('meta', {'name': 'viewport',
              'content': 'width=device-width, initial-scale=1, viewport-fit=cover'}),
]


def _js():
    lines = []
    for tag, attrs in HEAD:
        key = 'rel' if tag == 'link' else 'name'
        sel = f"{tag}[{key}='{attrs[key]}']"
        sets = "".join(f"e.setAttribute({k!r},{v!r});" for k, v in attrs.items())
        # Replace rather than append: Streamlit writes its own viewport and theme-color, and
        # a second one further down the head does not win.
        lines.append(
            f"(function(){{var d=window.parent.document;"
            f"var o=d.querySelector({sel!r});if(o)o.remove();"
            f"var e=d.createElement({tag!r});{sets}d.head.appendChild(e);}})();")
    return "\n".join(lines)


def install():
    """Inject the manifest and meta tags. Call once, near the top of the app."""
    if st.session_state.get("_pwa_done"):
        return
    components.html(f"<script>{_js()}</script>", height=0, width=0)
    st.session_state["_pwa_done"] = True
