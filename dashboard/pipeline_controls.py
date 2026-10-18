"""Responsive polling without shell access or database writes."""
import streamlit as st

from dashboard import pipeline_client

LABELS = {"running": "Running", "succeeded": "Succeeded", "failed": "Failed"}


@st.fragment(run_every="2s")
def render():
    try:
        state = pipeline_client.status()
    except pipeline_client.Unavailable as exc:
        st.button("Run Pipeline & Refresh", disabled=True)
        st.warning(str(exc))
        return
    current = state.get("current") or {}
    publication = state.get("publication") or {}
    running = current.get("status") == "running"
    st.subheader("Pipeline · " + LABELS.get(current.get("status"), "Idle"))
    if current:
        st.caption(f"Stage: {current['stage']} · Run: {current['id']}")
        if current.get("origin") == "test":
            st.caption("Controlled validation run (test origin).")
    st.caption("Last successful execution: " + str(publication.get("published_at") or "None yet"))
    if current.get("status") == "failed":
        # Backend errors are fixed application messages, never exception text.
        st.error(current.get("error") or "Pipeline failed; no successful refresh was confirmed.")
        st.caption("Showing the previous validated publication, if one exists.")
    if running:
        st.info("A run is already active. Status updates automatically; the last validated data remains available.")
    if st.button("Run Pipeline & Refresh", disabled=running, type="primary"):
        try:
            result = pipeline_client.trigger()
            if result["status"] == "already_running":
                st.info("Another run is already active; no duplicate run was started.")
            else:
                st.info("Pipeline started. Waiting for ingestion, dbt tests and publication.")
                st.rerun()
        except pipeline_client.Unavailable as exc:
            st.error(str(exc))
    generation = str(publication.get("run_id") or "")
    previous = st.session_state.get("publication_generation")
    st.session_state["publication_generation"] = generation
    if previous is not None and generation != previous and generation:
        # Current data queries are uncached. Clear future data caches as well,
        # then rerun the full page only after a committed successful publication.
        st.cache_data.clear()
        st.rerun()
    st.caption("Fixed workflow: Shopify → dbt build/tests → validated publication. Local demo access only.")
