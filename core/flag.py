"""'Looks wrong' on a number: the reason and the button press reach the app together.

The reason box sits in a form, so whatever was typed is sent with the click (or with Enter) in one go. A plain
text box commits its value only when it loses focus, and a click that raced that commit flagged the number with
the default 'looks wrong' instead of the reason the person wrote."""
import streamlit as st

DEFAULT = "Looks wrong"


def flag_number(store, obs_id: int, title: str, reason: str, user: str) -> str:
    """Flag one figure for the team and log it; returns the reason kept (the default when none was given)."""
    why = " ".join((reason or "").split()) or DEFAULT
    store.flag_observation(obs_id, why, user)
    store.log("flag", user, f"flagged '{title}': {why}")
    return why


def flag_form(store, obs_id: int, title: str, user: str, key: str) -> bool:
    """The reason box and the Flag button. True once the figure is flagged (the caller reruns the page)."""
    with st.form(f"flagform_{key}", clear_on_submit=True, border=False):
        why = st.text_input("What looks wrong?", key=f"why_{key}",
                            placeholder="Doesn't match the PDF; looks like the City figure")
        if st.form_submit_button("Flag for the team", type="primary"):
            flag_number(store, obs_id, title, why, user)
            return True
    return False
