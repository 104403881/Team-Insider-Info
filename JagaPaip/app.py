"""JagaPaip local decision dashboard."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from jagapaip.loader import file_signature, load_dataset
from jagapaip.theme import CSS
from jagapaip.views import render_app

ROOT = Path(__file__).resolve().parent


@st.cache_data(show_spinner=False)
def _load(root: str, signature: tuple) -> dict:
    # The signature is part of the cache key so a new team file is picked up.
    del signature
    return load_dataset(Path(root))


def main() -> None:
    st.set_page_config(
        page_title="JagaPaip",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)
    try:
        with st.spinner("Loading network files…"):
            dataset = _load(str(ROOT), file_signature(ROOT))
    except Exception as exc:  # noqa: BLE001 - show a recoverable screen instead of a stack dump
        st.error("JagaPaip could not load the network files.")
        st.caption("Check that files in the data folder are readable parquet or CSV, then refresh.")
        st.exception(exc)
        return
    render_app(dataset)


if __name__ == "__main__":
    main()
