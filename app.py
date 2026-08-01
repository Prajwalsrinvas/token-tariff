"""
TOKEN TARIFF — the entrypoint, and the only thing that decides what the sidebar
says.

Two pages: RATE CARD, the live cost calculator and model comparison, and WAGER,
a falsifiable claim about how long the frontier stays the frontier. Both live in
`pages_src/` and are named here rather than discovered from a `pages/` folder,
because folder discovery derives the sidebar labels from filenames and this app
has opinions about its own labels.

Streamlit Community Cloud runs `streamlit run app.py`, so this file stays the
entrypoint.
"""

import streamlit as st

st.set_page_config(page_title="TOKEN TARIFF", page_icon="▮", layout="wide")

# WAGER's path is pinned rather than derived from the filename: the page is
# linked to as /WAGER from the README, the scheduled email, and wager.json.
PAGES = [
    st.Page("pages_src/rate_card.py", title="RATE CARD", default=True),
    st.Page("pages_src/wager_page.py", title="WAGER", url_path="WAGER"),
]

st.navigation(PAGES).run()
