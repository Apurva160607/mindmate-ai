import os

import re

import time

import hmac

import html

import sqlite3

import secrets

import hashlib

import smtplib



from pathlib import Path

from email.message import EmailMessage



import streamlit as st



from home import inject_theme, render_home





# ============================================================

# 1. APP CONFIGURATION

# ============================================================



st.set_page_config(

    page_title="MINDMATE AI",

    page_icon="🌿",

    layout="wide",

    initial_sidebar_state="expanded",

)

# PWA manifest integration
st.html(
    """
    <script>
    (() => {
        if (!document.getElementById("mindmate-manifest")) {
            const link = document.createElement("link");
            link.id = "mindmate-manifest";
            link.rel = "manifest";
            link.href = "/app/static/manifest.json";
            document.head.appendChild(link);
        }
    })();
    </script>
    """,
    unsafe_allow_javascript=True
)



BASE_DIR = Path(__file__).resolve().parent

DB_PATH = BASE_DIR / "mindmate_users.db"



OTP_EXPIRY = 300

OTP_MAX_ATTEMPTS = 5

OTP_MAX_RESENDS = 3

OTP_RESEND_WAIT = 60





# ============================================================

# 2. SESSION STATE

# ============================================================



defaults = {

    "is_logged_in": False,

    "profile_name": "MATE",

    "user_key": None,

    "signup_pending": None,

    "login_otp_pending": None,

    "reset_otp_pending": None,

    "auth_notice": None,

}



for key, value in defaults.items():

    if key not in st.session_state:

        st.session_state[key] = value





# ============================================================

# 3. DATABASE

# ============================================================



def db_connect():

    conn = sqlite3.connect(DB_PATH, timeout=15)

    conn.row_factory = sqlite3.Row



    conn.execute("""

        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            username TEXT NOT NULL,

            contact_type TEXT NOT NULL,

            contact_value TEXT NOT NULL UNIQUE,

            password_hash TEXT NOT NULL,

            salt TEXT NOT NULL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

        )

    """)



    conn.commit()

    return conn





def normalize_contact(value):

    return value.strip().lower()





def valid_email(value):

    return bool(

        re.fullmatch(

            r"[^@\s]+@[^@\s]+\.[^@\s]+",

            value.strip()

        )

    )





# ============================================================

# 4. PASSWORD SECURITY

# ============================================================



def password_hash(password, salt=None):

    salt = salt or secrets.token_hex(16)



    digest = hashlib.pbkdf2_hmac(

        "sha256",

        password.encode("utf-8"),

        salt.encode("utf-8"),

        310_000

    ).hex()



    return digest, salt





def contact_taken(contact):

    with db_connect() as conn:

        row = conn.execute(

            "SELECT 1 FROM users WHERE contact_value = ?",

            (contact,)

        ).fetchone()



    return row is not None





def insert_user(pending):

    digest = pending["pw_hash"]

    salt = pending["salt"]



    try:

        with db_connect() as conn:

            conn.execute("""

                INSERT INTO users (

                    username,

                    contact_type,

                    contact_value,

                    password_hash,

                    salt

                )

                VALUES (?, ?, ?, ?, ?)

            """, (

                pending["username"],

                "Email",

                pending["contact_value"],

                digest,

                salt

            ))



            conn.commit()



        return True



    except sqlite3.IntegrityError:

        return False





def verify_login(contact, password):

    with db_connect() as conn:

        row = conn.execute("""

            SELECT username, password_hash, salt

            FROM users

            WHERE contact_value = ?

        """, (contact,)).fetchone()



    if not row:

        return None



    candidate, _ = password_hash(password, row["salt"])



    if hmac.compare_digest(candidate, row["password_hash"]):

        return row["username"]



    return None





def update_password(contact, password):

    digest, salt = password_hash(password)



    with db_connect() as conn:

        cursor = conn.execute("""

            UPDATE users

            SET password_hash = ?,

                salt = ?

            WHERE contact_value = ?

        """, (

            digest,

            salt,

            contact

        ))



        conn.commit()



        return cursor.rowcount > 0





# ============================================================

# 5. OTP RATE LIMITING

# ============================================================



def otp_send_allowed(contact, limit=5, window=3600):



    with db_connect() as conn:



        conn.execute("""

            CREATE TABLE IF NOT EXISTS otp_sends (

                contact TEXT NOT NULL,

                ts REAL NOT NULL

            )

        """)



        cutoff = time.time() - window



        conn.execute(

            "DELETE FROM otp_sends WHERE ts < ?",

            (cutoff,)

        )



        count = conn.execute("""

            SELECT COUNT(*)

            FROM otp_sends

            WHERE contact = ? AND ts >= ?

        """, (

            contact,

            cutoff

        )).fetchone()[0]



        if count >= limit:

            conn.commit()

            return False



        conn.execute("""

            INSERT INTO otp_sends (contact, ts)

            VALUES (?, ?)

        """, (

            contact,

            time.time()

        ))



        conn.commit()



    return True





# ============================================================

# 6. EMAIL CONFIGURATION

# ============================================================



def get_setting(name, default=""):



    value = os.getenv(name)



    if value:

        return value



    try:

        return str(st.secrets.get(name, default))

    except Exception:

        return default





def deliver_email_otp(destination, otp, purpose="verification"):



    host = get_setting("MINDMATE_SMTP_HOST")

    username = get_setting("MINDMATE_SMTP_USER")

    password = get_setting("MINDMATE_SMTP_PASSWORD")

    sender = get_setting("MINDMATE_EMAIL_FROM", username)



    try:

        port = int(

            get_setting("MINDMATE_SMTP_PORT", "587")

        )

    except ValueError:

        return False, "Invalid SMTP port configuration."



    if not all([host, username, password, sender]):

        return False, "Email service is not configured."



    message = EmailMessage()



    if purpose == "reset":

        message["Subject"] = "MINDMATE AI - Password Reset Code"

        description = "password reset"

    elif purpose == "login":

        message["Subject"] = "MINDMATE AI - Login Verification"

        description = "login verification"

    else:

        message["Subject"] = "MINDMATE AI - Email Verification"

        description = "email verification"



    message["From"] = sender

    message["To"] = destination



    message.set_content(f"""

Hello!



Your MINDMATE AI {description} code is:



{otp}



This code expires in 5 minutes.



If you did not request this code, please ignore this email.



MINDMATE AI

Your personal AI space.

""")



    try:

        with smtplib.SMTP(host, port, timeout=20) as server:

            server.starttls()

            server.login(username, password)

            server.send_message(message)



        return True, "A verification code was sent to your email."



    except Exception as e:
        print(f"SMTP ERROR: {type(e).__name__}")
        return False, "Email delivery failed. Check your email settings and try again."



def generate_otp():

    return f"{secrets.randbelow(1_000_000):06d}"





def otp_digest(otp):

    return hashlib.sha256(otp.encode()).hexdigest()





# ============================================================

# 7. AUTHENTICATION HELPERS

# ============================================================



def set_logged_in(username, email):



    user_key = "email:" + email.lower()



    st.session_state.is_logged_in = True

    st.session_state.profile_name = username

    st.session_state.user_key = user_key



    st.session_state.signup_pending = None

    st.session_state.login_otp_pending = None

    st.session_state.reset_otp_pending = None



    st.query_params.clear()

    st.rerun()





def save_google_notification_email():



    try:

        if not st.user.is_logged_in:

            return



        google_sub = st.user.get("sub")

        google_email = st.user.get("email")



        if not google_sub:

            return



        user_key = f"google:{google_sub}"



        st.session_state.is_logged_in = True

        st.session_state.profile_name = (

            st.user.get("name")

            or google_email

            or "MATE"

        )

        st.session_state.user_key = user_key



        if google_email:

            from reminders_store import save_notification_email



            save_notification_email(

                user_key,

                google_email

            )



    except Exception:

        pass





# ============================================================

# 8. THEME

# ============================================================



inject_theme()



st.markdown("""

<style>

@import url(

'https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600;700&family=DM+Sans:wght@400;500;600;700&display=swap'

);



html, body, .stApp {

    font-family: 'DM Sans', sans-serif !important;

    color: #30382C !important;

}



[data-testid="stAppViewContainer"] {

    background: #F8F9F4;

}



[data-testid="stHeader"] {

    background: transparent;

}



#MainMenu, footer {

    visibility: hidden;

}



.auth-header {

    display: flex;

    align-items: center;

    gap: 12px;

    padding: 16px 24px;

    margin-bottom: 30px;

    background: #FAFAF6;

    border-bottom: 1px solid #E7E9E1;

    border-radius: 12px;

}



.auth-logo {

    width: 38px;

    height: 38px;

    display: flex;

    align-items: center;

    justify-content: center;

    border-radius: 50%;

    background: #627657;

    color: white;

    font-size: 19px;

}



.auth-brand {

    font-size: 21px;

    font-weight: 700;

    color: #293326;

}



.auth-title {

    text-align: center;

    font-family: 'Playfair Display', serif;

    font-size: clamp(30px, 4vw, 42px);

    font-weight: 600;

    color: #30382C;

    margin: 12px 0 8px;

}



.auth-subtitle {

    text-align: center;

    color: #62695D;

    font-size: 15px;

    line-height: 1.7;

    margin-bottom: 25px;

}



.auth-note {

    text-align: center;

    color: #737A6E;

    font-size: 12px;

    margin-top: 18px;

}



[data-testid="stTextInput"] input {

    border-radius: 11px !important;

    border-color: #DCE1D5 !important;

    background: white !important;

}



div.stButton > button,

div.stFormSubmitButton > button {

    border-radius: 26px !important;

    min-height: 44px;

    font-weight: 700;

    border: 1px solid #647957;

    color: #647957;

    background: white;

}



div.stButton > button[kind="primary"],

div.stFormSubmitButton > button[kind="primary"] {

    background: #647957 !important;

    color: white !important;

    border-color: #647957 !important;

}



@media(max-width: 600px) {

    .auth-header {

        padding: 12px;

    }



    .auth-brand {

        font-size: 18px;

    }

}

</style>

""", unsafe_allow_html=True)





# ============================================================

# 9. AUTH HEADER

# ============================================================



def render_auth_header():
    st.markdown(
        """
        <div class="auth-header">
            <div class="auth-logo">🧠</div>
            <div class="auth-brand">MINDMATE AI</div>
        </div>
        """,
        unsafe_allow_html=True
    )





def render_auth_heading(title, subtitle):



    st.markdown(

        f'<div class="auth-title">{html.escape(title)}</div>',

        unsafe_allow_html=True

    )



    st.markdown(

        f'<div class="auth-subtitle">{html.escape(subtitle)}</div>',

        unsafe_allow_html=True

    )





# ============================================================

# 10. SIGNUP PAGE

# ============================================================



def render_signup():



    render_auth_heading(

        "Create your account",

        "Your personal AI space starts here."

    )



    pending = st.session_state.signup_pending



    if pending is None:



        with st.form("signup_form"):



            username = st.text_input(

                "Username",

                placeholder="What should we call you?"

            )



            email = st.text_input(

                "Email address",

                placeholder="you@example.com"

            )



            password = st.text_input(

                "Password",

                type="password",

                placeholder="At least 8 characters"

            )



            confirm = st.text_input(

                "Confirm password",

                type="password",

                placeholder="Enter password again"

            )



            submitted = st.form_submit_button(

                "CONTINUE TO VERIFICATION",

                type="primary",

                use_container_width=True

            )



        if submitted:



            contact = normalize_contact(email)



            if not username.strip():

                st.error("Please enter a username.")



            elif not valid_email(email):

                st.error("Enter a valid email address.")



            elif len(password) < 8:

                st.error("Password must contain at least 8 characters.")



            elif password != confirm:

                st.error("Passwords do not match.")



            elif contact_taken(contact):

                st.error(

                    "An account with this email already exists. "

                    "Please log in instead."

                )



                if st.button("GO TO LOGIN"):

                    st.query_params["page"] = "Log In"

                    st.rerun()



            elif not otp_send_allowed(contact):

                st.error(

                    "Too many verification codes were requested. "

                    "Please try again in an hour."

                )



            else:



                otp = generate_otp()

                sent, message = deliver_email_otp(contact, otp)



                if sent:



                    digest, salt = password_hash(password)



                    st.session_state.signup_pending = {

                        "username": username.strip(),

                        "contact_value": contact,

                        "pw_hash": digest,

                        "salt": salt,

                        "otp_hash": otp_digest(otp),

                        "expires": time.time() + OTP_EXPIRY,

                        "attempts": 0,

                        "resends": 0,

                        "last_sent": time.time(),

                    }



                    st.session_state.auth_notice = message

                    st.rerun()



                else:

                    st.error(message)



    else:



        pending = st.session_state.signup_pending



        notice = st.session_state.pop("auth_notice", None)



        if notice:

            st.success(notice)



        st.info(

            f"Enter the six-digit code sent to "

            f"{pending['contact_value']}. It expires in 5 minutes."

        )



        with st.form("verify_signup_form"):



            entered = st.text_input(

                "6-digit verification code",

                max_chars=6,

                placeholder="000000"

            )



            verify = st.form_submit_button(

                "VERIFY AND CREATE ACCOUNT",

                type="primary",

                use_container_width=True

            )



        if verify:



            if time.time() > pending["expires"]:



                st.session_state.signup_pending = None

                st.error("That code has expired. Please sign up again.")



            elif pending["attempts"] >= OTP_MAX_ATTEMPTS:



                st.session_state.signup_pending = None

                st.error("Too many attempts. Please start signup again.")



            elif not re.fullmatch(r"\d{6}", entered or ""):



                pending["attempts"] += 1

                st.error("Enter the six-digit code.")



            elif not hmac.compare_digest(

                otp_digest(entered),

                pending["otp_hash"]

            ):



                pending["attempts"] += 1

                st.error("Incorrect verification code.")



            elif insert_user(pending):



                set_logged_in(

                    pending["username"],

                    pending["contact_value"]

                )



            else:



                st.session_state.signup_pending = None

                st.error(

                    "An account with this email already exists. "

                    "Please log in."

                )



        wait = max(

            0,

            int(OTP_RESEND_WAIT - (

                time.time() - pending["last_sent"]

            ))

        )



        if st.button(

            "Resend code" if wait == 0 else f"Resend code (wait {wait}s)",

            disabled=wait > 0,

            use_container_width=True,

            key="signup_resend"

        ):



            if pending["resends"] >= OTP_MAX_RESENDS:



                st.error("Maximum resend attempts reached. Start signup again.")



            elif not otp_send_allowed(pending["contact_value"]):



                st.error("Too many OTP requests. Try again later.")



            else:



                otp = generate_otp()



                sent, message = deliver_email_otp(

                    pending["contact_value"],

                    otp

                )



                if sent:



                    pending.update({

                        "otp_hash": otp_digest(otp),

                        "expires": time.time() + OTP_EXPIRY,

                        "attempts": 0,

                        "resends": pending["resends"] + 1,

                        "last_sent": time.time(),

                    })



                    st.session_state.auth_notice = message

                    st.rerun()



                else:

                    st.error(message)



        if st.button("Cancel signup", use_container_width=True):

            st.session_state.signup_pending = None

            st.rerun()



    st.markdown(

        '<div class="auth-note">Already have an account?</div>',

        unsafe_allow_html=True

    )



    if st.button("LOG IN", use_container_width=True):

        st.session_state.signup_pending = None

        st.query_params["page"] = "Log In"

        st.rerun()





# ============================================================

# 11. LOGIN PAGE

# ============================================================



def render_login():



    render_auth_heading(

        "Welcome back",

        "A calmer space for everything that matters."

    )



    method = "Email"



    if method == "Google":



        st.markdown("**Continue with your Google account**")



        try:

            configured = bool(

                st.secrets.get("auth", {})

                .get("google", {})

                .get("client_id")

            )

        except Exception:

            configured = False



        if configured:



            if st.button(

                "Continue with Google",

                type="primary",

                use_container_width=True

            ):

                st.login("google")



        else:

            st.warning("Google sign-in is not configured.")



    elif method == "Apple":



        st.markdown("**Continue with Apple**")



        st.warning(

            "Apple sign-in is not configured yet. "

            "It requires an Apple Developer Services ID, "

            "a registered HTTPS domain and a validated OAuth callback."

        )



        st.caption(

            "Use email login or Google sign-in until Apple authentication "

            "is implemented."

        )



    else:



        with st.form("login_form"):



            email = st.text_input(

                "Email address",

                placeholder="you@example.com"

            )



            password = st.text_input(

                "Password",

                type="password",

                placeholder="Enter your password"

            )



            submitted = st.form_submit_button(

                "CONTINUE",

                type="primary",

                use_container_width=True

            )



        if submitted:



            contact = normalize_contact(email)



            if not valid_email(email) or not password:

                st.error("Enter a valid email address and password.")



            else:



                username = verify_login(contact, password)



                if username:

                    set_logged_in(username, contact)



                else:

                    st.error(

                        "Those details don't match an account. "

                        "Check them or sign up first."

                    )



    st.divider()



    left, right = st.columns(2)



    with left:

        if st.button("Forgot password?", use_container_width=True):

            st.session_state.login_otp_pending = None

            st.session_state.reset_otp_pending = None

            st.query_params["page"] = "Forgot Password"

            st.rerun()



    with right:

        if st.button("CREATE ACCOUNT", use_container_width=True):

            st.query_params["page"] = "Sign Up"

            st.rerun()



    

# 12. FORGOT PASSWORD

# ============================================================



def render_forgot_password():



    render_auth_heading(

        "Reset your password",

        "We'll help you securely recover your account."

    )



    pending = st.session_state.reset_otp_pending



    if pending is None:



        with st.form("forgot_password_form"):



            email = st.text_input(

                "Registered email address",

                placeholder="you@example.com"

            )



            submitted = st.form_submit_button(

                "SEND RESET CODE",

                type="primary",

                use_container_width=True

            )



        if submitted:



            contact = normalize_contact(email)



            if not valid_email(email):



                st.error("Enter a valid email address.")



            elif not otp_send_allowed(contact):



                st.error("Too many requests. Please try again later.")



            else:



                # Do not reveal whether an account exists.

                if contact_taken(contact):



                    otp = generate_otp()



                    sent, message = deliver_email_otp(

                        contact,

                        otp,

                        purpose="reset"

                    )



                    if sent:



                        st.session_state.reset_otp_pending = {

                            "email": contact,

                            "otp_hash": otp_digest(otp),

                            "expires": time.time() + OTP_EXPIRY,

                            "attempts": 0,

                        }



                        st.session_state.auth_notice = (

                            "If an account exists for this address, "

                            "a reset code has been sent."

                        )



                        st.rerun()



                    else:

                        st.error(message)



                else:



                    st.success(

                        "If an account exists for this address, "

                        "a reset code has been sent."

                    )



    else:



        pending = st.session_state.reset_otp_pending



        notice = st.session_state.pop("auth_notice", None)



        if notice:

            st.info(notice)



        with st.form("reset_verify_form"):



            st.text_input(

                "Registered email",

                value=pending["email"],

                disabled=True

            )



            entered = st.text_input(

                "Six-digit reset code",

                max_chars=6

            )



            new_password = st.text_input(

                "New password",

                type="password"

            )



            confirm_password = st.text_input(

                "Confirm new password",

                type="password"

            )



            submitted = st.form_submit_button(

                "RESET PASSWORD",

                type="primary",

                use_container_width=True

            )



        if submitted:



            if time.time() > pending["expires"]:



                st.session_state.reset_otp_pending = None

                st.error("Reset code expired. Request a new one.")



            elif pending["attempts"] >= OTP_MAX_ATTEMPTS:



                st.session_state.reset_otp_pending = None

                st.error("Too many attempts. Request a new code.")



            elif not re.fullmatch(r"\d{6}", entered or ""):



                pending["attempts"] += 1

                st.error("Enter the six-digit reset code.")



            elif not hmac.compare_digest(

                otp_digest(entered),

                pending["otp_hash"]

            ):



                pending["attempts"] += 1

                st.error("Incorrect reset code.")



            elif len(new_password) < 8:



                st.error("Password must contain at least 8 characters.")



            elif new_password != confirm_password:



                st.error("Passwords do not match.")



            elif update_password(

                pending["email"],

                new_password

            ):



                st.session_state.reset_otp_pending = None



                st.success(

                    "Your password has been reset successfully. "

                    "Please log in with your new password."

                )



                if st.button("GO TO LOGIN"):

                    st.query_params["page"] = "Log In"

                    st.rerun()



            else:

                st.error("Password reset failed. Please try again.")



    if st.button("BACK TO LOGIN"):

        st.session_state.reset_otp_pending = None

        st.query_params["page"] = "Log In"

        st.rerun()





# ============================================================

# 13. HOME AND REMINDERS NAVIGATION

# ============================================================



# ============================================================
# 13. MAIN ROUTER — one authenticated navigation system
# ============================================================

save_google_notification_email()
page = st.query_params.get("page", "Home")

if st.session_state.is_logged_in:
    legacy_pages = {"Reminders": "reminders", "Chatbot": "chat", "Vault": "vault", "Document Vault": "vault"}
    if page in legacy_pages:
        st.session_state["view"] = legacy_pages[page]
        st.query_params.clear()
    render_home()

else:



    render_auth_header()



    _, auth_col, _ = st.columns([1, 1.2, 1])



    with auth_col:



        if page == "Sign Up":

            render_signup()



        elif page == "Log In":

            render_login()



        elif page == "Forgot Password":

            render_forgot_password()



        elif page == "Reminders":



            st.warning(

                "Please log in to access your reminders."

            )



            if st.button("GO TO LOGIN"):

                st.query_params["page"] = "Log In"

                st.rerun()



        else:



            render_auth_heading(

                "Welcome to MINDMATE AI",

                "Your personal AI space starts here."

            )



            if st.button(

                "CREATE ACCOUNT",

                type="primary",

                use_container_width=True

            ):

                st.query_params["page"] = "Sign Up"

                st.rerun()



            if st.button(

                "LOG IN",

                use_container_width=True

            ):

                st.query_params["page"] = "Log In"

                st.rerun()



        st.markdown(

            '<div class="auth-note">'

            'Your personal space, thoughtfully organised'

            '</div>',

            unsafe_allow_html=True

        )
