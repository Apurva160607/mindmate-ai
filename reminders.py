
import html
from datetime import datetime, date, time
from zoneinfo import ZoneInfo

import streamlit as st
import reminders_store as store


def _local_datetime(utc_value):
    value = datetime.fromisoformat(utc_value)
    return value.astimezone()


def _format_datetime(utc_value):
    value = _local_datetime(utc_value)
    return value.strftime("%d %b %Y · %I:%M %p")


def _status(reminder):
    due = _local_datetime(reminder["due_at"])
    now = datetime.now().astimezone()

    if reminder["completed"]:
        return "Completed"

    if due < now:
        return "Overdue"

    return "Upcoming"


def _style():
    st.markdown("""
    <style>
    .stApp {
        background: #F7F7F2;
    }

    .st-key-reminders_page {
        width: 100%;
        max-width: 1160px;
        margin: 0 auto;
        padding: 0 clamp(8px, 2vw, 24px) 30px;
    }

    .st-key-reminders_header {
        width: 100%;
        margin: 4px 0 22px;
    }

    .st-key-reminders_header [data-testid="stButton"] button {
        min-height: 42px;
        border-radius: 13px;
        background: rgba(255,255,255,.88);
    }

    .reminder-heading {
        font-family: 'Playfair Display', serif;
        font-size: 38px;
        font-weight: 700;
        color: #354C3D;
        margin-bottom: 4px;
    }

    .reminder-subtitle {
        color: #758477;
        font-size: 15px;
        margin-bottom: 25px;
    }

    .reminder-card {
        background: #FFFFFF;
        border: 1px solid #DCE7D9;
        border-radius: 17px;
        padding: 18px;
        margin: 10px 0;
        box-shadow: 0 5px 18px rgba(65, 90, 67, .06);
    }

    .reminder-title {
        color: #344B3B;
        font-size: 17px;
        font-weight: 700;
        margin-bottom: 7px;
    }

    .reminder-notes {
        color: #718075;
        font-size: 13px;
        margin-bottom: 8px;
    }

    .reminder-meta {
        color: #819084;
        font-size: 12px;
    }

    div.stButton > button {
        border-radius: 10px;
        border: 1px solid #C9D9C7;
        color: #405C45;
        background: white;
    }

    div.stButton > button:hover {
        border-color: #718F72;
        color: #304C35;
    }

    div[data-testid="stForm"] {
        background: white;
        border: 1px solid #DCE7D9;
        border-radius: 17px;
        padding: 20px;
    }

    [data-testid="stSidebar"],
    section[data-testid="stSidebar"] {
        display: block !important;
        visibility: visible !important;
        width: 21rem !important;
        min-width: 21rem !important;
        max-width: 21rem !important;
        transform: none !important;
        margin-left: 0 !important;
        flex-shrink: 0 !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        width: 21rem !important;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: .65rem;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .65rem; }
    .mm-reminder-side-brand {
        color: #354C3D; font-size: 20px; font-weight: 800;
        padding: 8px 4px 18px; border-bottom: 1px solid #DCE7D9;
        margin-bottom: 12px;
    }
    .st-key-reminders_sidebar_active button {
        background: #E7F0E2 !important;
        border-color: #8DA783 !important;
        color: #304C35 !important;
    }
    </style>
    """, unsafe_allow_html=True)


def _reminders_sidebar(name, dock):
    """Shared left navigation used across the signed-in MINDMATE pages."""
    with st.sidebar:
        st.markdown('<div class="mm-reminder-side-brand">🧠 MINDMATE AI</div>', unsafe_allow_html=True)
        if st.button("Dashboard", key="reminders_nav_dashboard", icon=":material/dashboard:", width="stretch"):
            st.session_state["view"] = "dashboard"
            st.rerun()
        if st.button("Chatbot", key="reminders_nav_chat", icon=":material/chat:", width="stretch"):
            st.session_state["view"] = "chat"
            st.rerun()
        if st.button("Document Vault", key="reminders_nav_vault", icon=":material/lock:", width="stretch"):
            st.session_state["view"] = "vault"
            st.rerun()
        with st.container(key="reminders_sidebar_active"):
            st.button("Reminders", key="reminders_nav_current", icon=":material/notifications:",
                      width="stretch", disabled=True)
        st.divider()
        if dock and name:
            dock(name, key="chat_dock")


def render_reminders(user_key, name=None, dock=None):
    if not user_key:
        st.error("Please log in to access your reminders.")
        return

    _style()
    _reminders_sidebar(name, dock)

    with st.container(key="reminders_page"):
        with st.container(key="reminders_header"):
            back_col, title_col, spacer_col = st.columns([1.15, 3.7, 1.55], vertical_alignment="center")
            with back_col:
                if st.button("← Dashboard", key="reminders_back", width="stretch"):
                    st.session_state["view"] = "dashboard"
                    st.rerun()
            with title_col:
                st.markdown('<div class="reminder-heading">Your Reminders 🌿</div>', unsafe_allow_html=True)
                st.markdown(
                    '<div class="reminder-subtitle">'
                    'A little reminder for everything that matters.'
                    '</div>',
                    unsafe_allow_html=True
                )

        reminders = store.list_reminders(user_key)

        upcoming = [r for r in reminders if _status(r) == "Upcoming"]
        overdue = [r for r in reminders if _status(r) == "Overdue"]
        completed = [r for r in reminders if _status(r) == "Completed"]

        # Summary cards
        c1, c2, c3 = st.columns(3)

        with c1:
            st.metric("Upcoming", len(upcoming))

        with c2:
            st.metric("Overdue", len(overdue))

        with c3:
            st.metric("Completed", len(completed))

        st.divider()

        # Create reminder
        with st.expander("＋ Create a new reminder", expanded=True):
            with st.form("create_reminder_form", clear_on_submit=True):

                title = st.text_input(
                    "Reminder title",
                    placeholder="e.g. Pay electricity bill"
                )

                notes = st.text_area(
                    "Additional notes",
                    placeholder="Add any details you need..."
                )

                col1, col2 = st.columns(2)

                with col1:
                    due_date = st.date_input(
                        "Date",
                        value=date.today()
                    )

                with col2:
                    due_time = st.time_input(
                        "Time",
                        value=time(9, 0),
                        format="12h"
                    )

                repeat_rule = st.selectbox(
                    "Repeat",
                    ["none", "daily", "weekly", "monthly"],
                    format_func=lambda x: {
                        "none": "Does not repeat",
                        "daily": "Every day",
                        "weekly": "Every week",
                        "monthly": "Every month"
                    }[x]
                )

                submitted = st.form_submit_button(
                    "＋ Save reminder",
                    use_container_width=True,
                    type="primary"
                )

                if submitted:
                    if not title.strip():
                        st.error("Please enter a reminder title.")

                    else:
                        local_due = datetime.combine(
                            due_date,
                            due_time
                        ).astimezone()

                        try:
                            store.create_reminder(
                                user_key=user_key,
                                title=title,
                                notes=notes,
                                due_at=local_due,
                                repeat_rule=repeat_rule
                            )

                            st.success("Your reminder has been saved!")
                            st.rerun()

                        except ValueError as exc:
                            st.error(str(exc))

        st.divider()

        # Reminder filters
        selected_tab = st.radio(
            "View reminders",
            ["All", "Upcoming", "Overdue", "Completed"],
            horizontal=True,
            label_visibility="collapsed"
        )

        if selected_tab == "Upcoming":
            visible = upcoming
        elif selected_tab == "Overdue":
            visible = overdue
        elif selected_tab == "Completed":
            visible = completed
        else:
            visible = reminders

        if not visible:
            st.info("Nothing here yet. Create a reminder to get started.")

        for reminder in visible:
            status = _status(reminder)

            with st.container(border=True):
                col1, col2 = st.columns([5, 1])

                with col1:
                    safe_title = html.escape(reminder["title"])
                    safe_notes = html.escape(reminder["notes"] or "")

                    st.markdown(
                        f"""
                        <div class="reminder-title">{safe_title}</div>
                        <div class="reminder-notes">{safe_notes}</div>
                        <div class="reminder-meta">
                        🕒 {_format_datetime(reminder["due_at"])}
                        &nbsp; · &nbsp;
                        🔁 {html.escape(reminder["repeat_rule"].title())}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                with col2:
                    if status == "Completed":
                        st.success("Done")
                    elif status == "Overdue":
                        st.warning("Overdue")
                    else:
                        st.info("Upcoming")

                button_col1, button_col2, button_col3 = st.columns(3)

                with button_col1:
                    if status != "Completed":
                        if st.button(
                            "✓ Complete",
                            key=f"complete_{reminder['id']}"
                        ):
                            store.set_completed(
                                user_key,
                                reminder["id"],
                                True
                            )
                            st.rerun()
                    else:
                        if st.button(
                            "↩ Reopen",
                            key=f"reopen_{reminder['id']}"
                        ):
                            store.set_completed(
                                user_key,
                                reminder["id"],
                                False
                            )
                            st.rerun()

                with button_col2:
                    if st.button(
                        "✎ Edit",
                        key=f"edit_{reminder['id']}"
                    ):
                        st.session_state["editing_reminder"] = reminder["id"]
                        st.rerun()

                with button_col3:
                    if st.button(
                        "Delete",
                        key=f"delete_{reminder['id']}"
                    ):
                        store.delete_reminder(
                            user_key,
                            reminder["id"]
                        )
                        st.rerun()

            # Edit selected reminder
            if st.session_state.get("editing_reminder") == reminder["id"]:

                local_due = _local_datetime(reminder["due_at"])

                with st.expander("Edit reminder", expanded=True):
                    with st.form(f"edit_form_{reminder['id']}"):

                        new_title = st.text_input(
                            "Title",
                            value=reminder["title"],
                            key=f"edit_title_{reminder['id']}"
                        )

                        new_notes = st.text_area(
                            "Notes",
                            value=reminder["notes"],
                            key=f"edit_notes_{reminder['id']}"
                        )

                        e1, e2 = st.columns(2)

                        with e1:
                            new_date = st.date_input(
                                "Date",
                                value=local_due.date(),
                                key=f"edit_date_{reminder['id']}"
                            )

                        with e2:
                            new_time = st.time_input(
                                "Time",
                                value=local_due.time().replace(
                                    second=0,
                                    microsecond=0
                                ),
                                key=f"edit_time_{reminder['id']}",
                                format="12h"
                            )

                        new_repeat = st.selectbox(
                            "Repeat",
                            ["none", "daily", "weekly", "monthly"],
                            index=[
                                "none", "daily", "weekly", "monthly"
                            ].index(reminder["repeat_rule"]),
                            key=f"edit_repeat_{reminder['id']}"
                        )

                        save_col, cancel_col = st.columns(2)

                        with save_col:
                            save = st.form_submit_button(
                                "Save changes",
                                use_container_width=True
                            )

                        with cancel_col:
                            cancel = st.form_submit_button(
                                "Cancel",
                                use_container_width=True
                            )

                        if save:
                            new_due = datetime.combine(
                                new_date,
                                new_time
                            ).astimezone()

                            try:
                                store.update_reminder(
                                    user_key,
                                    reminder["id"],
                                    new_title,
                                    new_notes,
                                    new_due,
                                    new_repeat
                                )

                                st.session_state.pop(
                                    "editing_reminder",
                                    None
                                )

                                st.success("Reminder updated.")
                                st.rerun()

                            except ValueError as exc:
                                st.error(str(exc))

                        if cancel:
                            st.session_state.pop(
                                "editing_reminder",
                                None
                            )
                            st.rerun()

