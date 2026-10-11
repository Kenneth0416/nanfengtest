"""A tool's chart spec ({type, title, x, series, unit}) drawn as a Plotly figure in the house colours.

Streamlit gives an element without a key an id made from its arguments, so two identical charts on one page (the
same trend asked about twice in a conversation) collide and the page shows an error instead. Every chart is
therefore drawn with a key the caller makes unique for the run."""
from __future__ import annotations

import hashlib
import json

import plotly.graph_objects as go


def figure(spec: dict) -> go.Figure:
    fig = go.Figure()
    for s in spec["series"]:
        if spec["type"] == "bar":
            fig.add_bar(x=spec["x"], y=s["values"], name=s["name"], marker_color="#1B3A5C")
        else:
            fig.add_scatter(x=spec["x"], y=s["values"], name=s["name"], mode="lines+markers",
                            line_shape="hv" if spec["type"] == "step" else "linear",
                            line=dict(dash="dot", color="#6B7A90") if s["name"] == "Long-term average"
                            else dict(color="#1B3A5C"))
    fig.update_layout(title=spec["title"], yaxis_title=spec.get("unit", ""), height=300,
                      margin=dict(l=10, r=10, t=40, b=10), legend=dict(orientation="h"),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def fingerprint(spec: dict) -> str:
    """The same chart gives the same fingerprint: used to show it once per answer and to name its key."""
    return hashlib.sha1(json.dumps(spec, sort_keys=True, default=str).encode()).hexdigest()[:12]


def show(spec: dict | None, key: str) -> None:
    import streamlit as st
    if spec:
        st.plotly_chart(figure(spec), width="stretch", key=key)
