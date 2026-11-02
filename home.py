"""home.py - Sage Sky light theme and the (unauthenticated + signed-in) home page.

Day 1 goals:
  * one shared light theme for every page (inject_theme)
  * a home page built from NATIVE Streamlit widgets, so clicking a button
    never reloads the browser and never wipes st.session_state
"""
import base64
import html as html_lib

import streamlit as st

# --- Real brand marks (inline SVG, no external files) ----------------------
GOOGLE_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.76 7.18l7.73 6C44.42 37.92 46.98 31.7 46.98 24.55z"/><path fill="#FBBC05" d="M10.53 28.59A14.4 14.4 0 0 1 9.75 24c0-1.59.27-3.13.76-4.59l-7.98-6.19A23.9 23.9 0 0 0 0 24c0 3.87.93 7.52 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.91-5.8l-7.73-6c-2.15 1.45-4.9 2.3-8.18 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>'''
APPLE_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#000000"><path d="M16.37 12.3c.02 2.1 1.84 2.8 1.86 2.81-.02.05-.29 1.01-.96 2-.58.86-1.18 1.72-2.12 1.74-.92.02-1.22-.56-2.28-.56-1.05 0-1.39.54-2.26.58-.9.03-1.58-.94-2.16-1.8-1.18-1.72-2.08-4.86-.87-6.98.6-1.05 1.68-1.72 2.85-1.74.89-.02 1.73.61 2.28.61.54 0 1.55-.75 2.61-.64.44.02 1.69.18 2.49 1.35-.06.04-1.49.87-1.47 2.63ZM14.66 6.95c.48-.58.8-1.39.71-2.2-.69.03-1.52.46-2.02 1.04-.44.51-.83 1.33-.73 2.11.77.06 1.56-.39 2.04-.95Z"/></svg>'''

# --- Faint decorative line art (drawn as CSS backgrounds) ------------------
_S = 'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#7F9474" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"'
CHIP_SVG = f'<svg {_S}><rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"/></svg>'
CODE_SVG = f'<svg {_S}><path d="M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/></svg>'
ROBOT_SVG = f'<svg {_S}><rect x="5" y="8" width="14" height="11" rx="3"/><path d="M12 4v4"/><circle cx="12" cy="3.5" r="1"/><circle cx="9.5" cy="13" r="1.2"/><circle cx="14.5" cy="13" r="1.2"/><path d="M9.5 16.5h5M3 12v3M21 12v3"/></svg>'
NODES_SVG = f'<svg {_S}><circle cx="6" cy="7" r="2"/><circle cx="18" cy="6" r="2"/><circle cx="12" cy="12" r="2.2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/><path d="M7.7 8l2.9 2.8M16.4 7.4l-3.2 3.4M7.6 16.8l2.9-3M16.4 16.6l-3.1-3"/></svg>'
CIRCUIT_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160">'
    '<g fill="none" stroke="#7F9474" stroke-width="1.2" stroke-linecap="round">'
    '<path d="M0 40h50l14 14h40"/><path d="M160 110h-46l-14-14H60"/>'
    '<path d="M80 0v34l12 12"/><path d="M80 160v-30l-12-12"/></g>'
    '<g fill="#7F9474"><circle cx="104" cy="54" r="3"/><circle cx="60" cy="96" r="3"/>'
    '<circle cx="92" cy="46" r="2.5"/><circle cx="68" cy="118" r="2.5"/></g></svg>'
)


def _uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


_THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600;700&family=DM+Sans:wght@400;500;600;700&display=swap');
:root{--sage:#647957;--sage-d:#53664A;--ink:#30382C;--muted:#62695D;--line:#DCE1D5}
html, body {background:#F2F6EE !important;}
.stApp{background:linear-gradient(180deg,#EAF1E6 0%,#F4F8F1 48%,#FFFFFF 100%) !important;
  color:var(--ink) !important;font-family:'DM Sans','Segoe UI',system-ui,sans-serif;}
#root,[data-testid="stAppViewContainer"],[data-testid="stMain"],[data-testid="stMainBlockContainer"],
.block-container,[data-testid="stHeader"]{background:transparent !important;}
[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],
#MainMenu,footer{display:none !important;}
[data-testid="stMain"]{position:relative;z-index:1;}
.block-container,[data-testid="stMainBlockContainer"]{max-width:100% !important;padding:0 18px 36px !important;}

/* faint circuit traces, fading out toward the centre */
[data-testid="stAppViewContainer"]::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;
  background-image:url("__CIRCUIT__");background-size:160px;opacity:.17;
  -webkit-mask-image:radial-gradient(ellipse at 50% 45%,transparent 40%,#000 92%);
  mask-image:radial-gradient(ellipse at 50% 45%,transparent 40%,#000 92%);}

/* restrained AI icons */
.mm-deco{position:fixed;inset:0;z-index:0;pointer-events:none;}
.mm-deco i{position:absolute;display:block;width:clamp(56px,7vw,92px);aspect-ratio:1;opacity:.42;
  background-repeat:no-repeat;background-position:center;background-size:contain;}
.mm-deco .d1{left:6%;top:20%;background-image:url("__NODES__");transform:rotate(-8deg);}
.mm-deco .d2{right:7%;top:16%;background-image:url("__CHIP__");transform:rotate(7deg);}
.mm-deco .d3{left:9%;bottom:12%;background-image:url("__CODE__");transform:rotate(6deg);}
.mm-deco .d4{right:10%;bottom:14%;background-image:url("__ROBOT__");transform:rotate(-6deg);}
@media(max-width:700px){.mm-deco .d3,.mm-deco .d4{display:none;}.mm-deco i{opacity:.3;}}

/* readable text on every page (the old CSS forced near-white text) */
.stApp [data-testid="stMarkdownContainer"] p,.stApp [data-testid="stMarkdownContainer"] li,
.stApp [data-testid="stMarkdownContainer"] strong,.stApp [data-testid="stMarkdownContainer"] em{color:var(--ink) !important;}
.stApp [data-testid="stCaptionContainer"]{color:var(--muted) !important;}
.stApp button [data-testid="stMarkdownContainer"] p{color:inherit !important;}
/* breathing room (the old CSS set every gap to 0) */
[data-testid="stMain"] [data-testid="stVerticalBlock"]{gap:.8rem !important;}

/* header */
.mm-header{height:68px;display:flex;align-items:center;gap:11px;padding:0 clamp(8px,4vw,54px);
  margin:0 -18px 8px;background:rgba(255,255,255,.55);-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);
  border-bottom:1px solid rgba(220,225,213,.9);}
.mm-logo{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  background:var(--sage);font-size:18px;}
.mm-brand{font:700 21px 'DM Sans',sans-serif;letter-spacing:-.5px;color:#293326;}

/* hero */
.mm-title{text-align:center;font:600 clamp(46px,8vw,84px)/1.05 'Playfair Display',Georgia,serif;
  letter-spacing:-2px;margin:clamp(24px,7vh,64px) 0 14px;color:var(--ink);}
.mm-title span{color:var(--sage);}
.mm-sub{text-align:center;color:var(--muted);font:17px/1.7 'DM Sans',sans-serif;max-width:520px;margin:0 auto 26px;}
.mm-note{text-align:center;color:#737A6E;font-size:12.5px;margin-top:6px;}

/* frosted sign-in card */
.st-key-home_card{background:rgba(255,255,255,.58);-webkit-backdrop-filter:blur(16px);backdrop-filter:blur(16px);
  border:1px solid rgba(255,255,255,.9);border-radius:24px;padding:22px 24px 18px;
  box-shadow:0 18px 50px rgba(85,108,76,.13),0 2px 6px rgba(85,108,76,.06);}
.st-key-home_card [data-testid="stVerticalBlock"]{gap:.8rem !important;}

/* buttons */
div.stButton > button{border-radius:14px;min-height:50px;font-weight:600;border:1px solid var(--line);
  background:#fff;color:var(--ink);transition:border-color .15s,background .15s,box-shadow .15s;}
div.stButton > button:hover{border-color:var(--sage);color:var(--sage-d);background:#F4F8F1;box-shadow:0 4px 14px rgba(100,121,87,.12);}
div.stButton > button:focus-visible{outline:3px solid rgba(100,121,87,.35);outline-offset:2px;}
div.stButton > button[kind="primary"]{background:var(--sage);border-color:var(--sage);color:#fff;}
div.stButton > button[kind="primary"]:hover{background:var(--sage-d);color:#fff;}
.st-key-btn_google button p::before,.st-key-btn_apple button p::before{content:"";display:inline-block;
  width:20px;height:20px;margin-right:12px;vertical-align:-4px;background-repeat:no-repeat;
  background-position:center;background-size:contain;}
.st-key-btn_google button p::before{background-image:url("__GOOGLE_URI__");}
.st-key-btn_apple button p::before{background-image:url("__APPLE_URI__");}
/* dashboard */
.mm-title.sm{font-size:clamp(34px,6vw,58px);margin:clamp(20px,6vh,52px) 0 10px;}
.mm-feat-note{text-align:center;color:var(--muted);font-size:13.5px;margin-top:2px;}
[class*="st-key-feat_"] button{min-height:132px;border-radius:22px;font-size:18px;font-weight:700;
  background:rgba(255,255,255,.72);-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);
  box-shadow:0 10px 30px rgba(85,108,76,.10);}
[class*="st-key-feat_"] button:hover{transform:translateY(-2px);box-shadow:0 16px 38px rgba(85,108,76,.18);}
.mm-soon{background:rgba(255,255,255,.7);border:1px solid var(--line);border-radius:20px;padding:20px 22px;
  color:var(--muted);text-align:center;line-height:1.7;}

/* account chip, bottom-left, with a drop-up menu */
.st-key-account_dock{position:fixed !important;left:16px;bottom:16px;width:min(250px,calc(100vw - 32px));z-index:999;}
.st-key-account_dock [data-testid="stVerticalBlock"]{gap:.5rem !important;}
.st-key-btn_account button{justify-content:flex-start;background:rgba(255,255,255,.92);border-radius:16px;
  box-shadow:0 8px 24px rgba(85,108,76,.16);}
.st-key-btn_account button{height:auto !important;min-height:48px;white-space:normal !important;}
.st-key-btn_account button [data-testid="stMarkdownContainer"] p{white-space:normal !important;overflow-wrap:anywhere !important;text-align:left;line-height:1.25;}
.st-key-account_panel{background:#fff;border:1px solid var(--line);border-radius:16px;padding:8px;
  box-shadow:0 12px 30px rgba(85,108,76,.20);}
/* bigger, bolder, higher-contrast text everywhere */
:root{--ink:#1B2418;--muted:#3F4A3B;--sage:#5A8449;--sage-d:#456B38;--line:#C4CFBC}
html{font-size:112.5% !important;}
.stApp,.stApp p,.stApp li,.stApp label,.stApp span,.stApp input,.stApp textarea,.stApp button{font-weight:600;}
.stApp h1,.stApp h2,.stApp h3{font-weight:700 !important;}
.stApp [data-testid="stWidgetLabel"] p{font-size:1.02rem !important;font-weight:700 !important;color:var(--ink) !important;}
.stApp input,.stApp textarea{font-size:1.05rem !important;font-weight:600 !important;color:var(--ink) !important;}
.stApp input::placeholder,.stApp textarea::placeholder{color:#5F6B59 !important;font-weight:500 !important;}
.stApp [data-testid="stCaptionContainer"],.stApp .mm-note,.stApp .mm-feat-note,.stApp .auth-note{
  font-size:.95rem !important;font-weight:600 !important;color:var(--muted) !important;}
.stApp .mm-sub,.stApp .auth-subtitle{font-size:1.2rem !important;font-weight:600 !important;color:var(--muted) !important;line-height:1.6 !important;}
.stApp .mm-brand,.stApp .auth-brand{font-size:1.4rem !important;font-weight:800 !important;color:var(--ink) !important;}
.stApp div.stButton > button,.stApp div.stFormSubmitButton > button{font-size:1.05rem !important;font-weight:700 !important;}
.stApp [data-testid="stAlert"] p{font-size:1.02rem !important;font-weight:600 !important;}
.stApp [data-testid="stMarkdownContainer"] p,.stApp [data-testid="stMarkdownContainer"] li{font-size:1.05rem;}
/* MINDMATE AI — quieter, cleaner background */
[data-testid="stAppViewContainer"]::before {
    opacity: 0.07 !important;
}

.mm-deco i {
    opacity: 0.20 !important;
}

@media (max-width: 700px) {
    .mm-deco {
        display: none !important;
    }

    .mm-header {
        height: 60px;
        padding: 0 16px;
    }

    .mm-title {
        letter-spacing: -1px;
        margin-top: 28px;
    }

    .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-left: 14px !important;
        padding-right: 14px !important;
    }
}
</style>
"""

_DECO_HTML = '<div class="mm-deco"><i class="d1"></i><i class="d2"></i><i class="d3"></i><i class="d4"></i></div>'
_HEADER_HTML = '<div class="mm-header"><div class="mm-logo">\U0001F9E0</div><div class="mm-brand">MINDMATE AI</div></div>'


def inject_theme() -> None:
    """Apply the light Sage Sky theme. Call once, near the top of app.py."""
    css = (
        _THEME_CSS.replace("__CIRCUIT__", _uri(CIRCUIT_SVG))
        .replace("__NODES__", _uri(NODES_SVG))
        .replace("__CHIP__", _uri(CHIP_SVG))
        .replace("__CODE__", _uri(CODE_SVG))
        .replace("__ROBOT__", _uri(ROBOT_SVG))
        .replace("__GOOGLE_URI__", _uri(GOOGLE_SVG))
        .replace("__APPLE_URI__", _uri(APPLE_SVG))
    )
    st.markdown(css, unsafe_allow_html=True)


def go(page: str, **params: str) -> None:
    """Navigate WITHOUT a browser reload (a reload would wipe st.session_state)."""
    st.query_params.from_dict({"page": page, **params})
    st.rerun()


def _google_configured() -> bool:
    try:
        return bool(st.secrets.get("auth", {}).get("google", {}).get("client_id"))
    except Exception:
        return False


def logout() -> None:
    """Clear this browser session; also end the Google session if one exists."""
    google_session = False
    try:
        google_session = bool(st.user.is_logged_in)
    except Exception:
        pass
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    if google_session:
        st.logout()
    else:
        st.query_params.clear()
        st.rerun()


_VIEWS = {
    "reminders": ("Reminders", "Appointments, medication, bills and due dates. Built in Day 6."),
}


def _account_dock(name: str, above=None, key: str = "account_dock") -> None:
    """Account chip fixed at the bottom-left; click it to open a drop-up with Log out."""
    with st.container(key=key):
        if above is not None:
            above()                       # e.g. the usage card, shown directly above the name
        if st.session_state.get("menu_open"):
            with st.container(key="account_panel"):
                if st.button("Log out", key="btn_logout", icon=":material/logout:", width="stretch"):
                    logout()
        label = name
        if st.button(label, key="btn_account", icon=":material/account_circle:", width="stretch"):
            st.session_state.menu_open = not st.session_state.get("menu_open", False)
            st.rerun()


def _render_dashboard() -> None:
    name = str(st.session_state.get("profile_name", "mate")).strip() or "mate"
    first = html_lib.escape(name.split()[0])
    view = st.session_state.get("view", "dashboard")
    if view == "vault":
        from vault import render_vault       # imported here to avoid a circular import
        render_vault(st.session_state.get("user_key"), name, _account_dock)
        return
    if view == "chat":
        from chatbot import render_chat      # imported here to avoid a circular import
        render_chat(st.session_state.get("user_key"), name, _account_dock)
        return
    if view == "reminders":
        from reminders import render_reminders
        render_reminders(st.session_state.get("user_key"), name, _account_dock)
        return
    _, mid, _ = st.columns([0.4, 3, 0.4])
    with mid:
        if view in _VIEWS:
            title, text = _VIEWS[view]
            st.markdown(f'<div class="mm-title sm">{title}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="mm-soon"><b>Coming soon.</b><br>{text}</div>', unsafe_allow_html=True)
            if st.button("\u2190 Back to dashboard", key="btn_back", width="stretch"):
                st.session_state.view = "dashboard"
                st.rerun()
        else:
            st.markdown(f'<div class="mm-title sm">Hello <span>{first}.</span></div>'
                        '<div class="mm-sub">What would you like to do today?</div>',
                        unsafe_allow_html=True)
            cols = st.columns(3)
            items = [("chat", "Chatbot", ":material/chat:", "Talk to your AI assistant"),
                     ("vault", "Vault", ":material/lock:", "Your secure documents"),
                     ("reminders", "Reminders", ":material/notifications:", "Never miss a due date")]
            for col, (key, label, icon, note) in zip(cols, items):
                with col:
                    if st.button(label, key=f"feat_{key}", icon=icon, width="stretch"):
                        st.session_state.view = key
                        st.rerun()
                    st.markdown(f'<div class="mm-feat-note">{note}</div>', unsafe_allow_html=True)
    _account_dock(name)


def render_home() -> None:
    logged_in = st.session_state.get("is_logged_in", False)
    if not (logged_in and st.session_state.get("view") in ("chat", "vault", "reminders")):
        st.markdown(_DECO_HTML + _HEADER_HTML, unsafe_allow_html=True)
    if logged_in:
        _render_dashboard()      # top level on purpose: the chat box can only dock to the bottom here
        return
    _, mid, _ = st.columns([1, 1.5, 1])
    with mid:
        st.markdown('<div class="mm-title">Hello <span>mate.</span></div>'
                    '<div class="mm-sub">MINDMATE AI is your personal assistant: chat with an AI, '
                    'keep important documents in one place, and never miss a reminder.</div>',
                    unsafe_allow_html=True)
        with st.container(key="home_card"):
            if st.button("Continue with Google", key="btn_google", width="stretch"):
                if _google_configured():
                    st.login("google")      # Google's official account chooser
                else:
                    go("Log In", method="Google")   # shows the "not configured yet" help
            if st.button("Continue with Apple", key="btn_apple", width="stretch"):
                go("Log In", method="Apple")
            if st.button("Continue with email", key="btn_email", type="primary", width="stretch"):
                go("Log In", method="Email")
        st.markdown('<div class="mm-note">A calmer space for everything that matters.</div>',
                    unsafe_allow_html=True)
