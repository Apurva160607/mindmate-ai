"""MINDMATE AI — Document Vault (Sage Sky light theme).

Keeps storage and ownership checks in vault_store.py. This file is presentation and
workflow only: every operation passes the server-side user_key to the store.
"""
import html as html_lib
import mimetypes
import time

import streamlit as st

import attachments as att
import vault_store as store


_FILE_STYLE = {
    ".pdf": ("PDF", "📕", "pdf"),
    ".docx": ("WORD", "📘", "word"),
    ".txt": ("TEXT", "📄", "text"),
    ".png": ("IMAGE", "🖼️", "image"),
    ".jpg": ("IMAGE", "🖼️", "image"),
    ".jpeg": ("IMAGE", "🖼️", "image"),
    ".webp": ("IMAGE", "🖼️", "image"),
}

_VAULT_CSS = """
<style>
/* Page geometry */
[data-testid="stMain"] .block-container { padding-top: 1.1rem !important; padding-bottom: 130px !important; }
.st-key-vault_page { width: 100%; max-width: 1240px; margin: 0 auto; padding: 0 clamp(8px, 2vw, 24px); }
.st-key-vault_page [data-testid="stVerticalBlock"] { gap: .85rem; }
.st-key-vault_page [data-testid="stHorizontalBlock"] { align-items: stretch; gap: 1rem; }

/* Header */
.st-key-vault_header { margin: 4px 0 8px; }
.st-key-vault_header [data-testid="stHorizontalBlock"] { align-items: center !important; }
.st-key-vault_back button { min-height: 42px; border-radius: 13px !important; background: rgba(255,255,255,.8) !important; }
.vault-heading { text-align: center; color: #111810; font-family: 'Playfair Display', Georgia, serif;
    font-size: clamp(2rem, 3.5vw, 2.8rem); font-weight: 700; letter-spacing: -.035em; line-height: 1.12; margin: 0; }
.vault-subheading { text-align: center; color: #4D5A48; font-size: .98rem; margin: 7px 0 2px; }
.vault-usage { text-align: right; color: #43533C; font-size: .88rem; font-weight: 700; line-height: 1.5; }
.vault-section-title { color: #20291D; font-size: 1.04rem; font-weight: 800; margin: 4px 0 0; }
.vault-helper { color: #596653; font-size: .9rem; }

/* Search and filters */
.st-key-vault_filters [data-testid="stHorizontalBlock"] { align-items: center !important; }
.st-key-vault_filters [data-baseweb="input"], .st-key-vault_filters [data-baseweb="select"] {
    border-radius: 14px !important; background: rgba(255,255,255,.9) !important;
}
.st-key-vault_filters input { color: #111810 !important; }
.st-key-vault_filters [data-testid="stWidgetLabel"] { display: none; }

/* Document cards */
.st-key-vault_grid [data-testid="stHorizontalBlock"] { align-items: stretch !important; gap: 1rem !important; }
[class*="st-key-vcard_"] {
    min-height: 225px; height: 100%; display: flex; flex-direction: column; justify-content: space-between;
    padding: 18px 18px 15px; border-radius: 21px;
    background: linear-gradient(145deg, rgba(255,255,255,.96), rgba(248,250,245,.92));
    border: 1px solid rgba(194,207,185,.95);
    box-shadow: 0 8px 25px rgba(63,82,53,.075);
    transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
[class*="st-key-vcard_"]:hover {
    transform: translateY(-3px); border-color: #9BAF8D;
    box-shadow: 0 15px 32px rgba(63,82,53,.14);
}
.st-key-vcard_add {
    background: linear-gradient(145deg, rgba(250,253,248,.9), rgba(234,242,229,.72));
    border: 1.5px dashed #9CAE91; text-align: center; justify-content: center;
}
.vc-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.vc-icon { display: inline-flex; align-items: center; justify-content: center; width: 49px; height: 49px;
    border-radius: 15px; font-size: 1.65rem; background: #EDF3E8; border: 1px solid #DFE8D8; }
.vc-type { display: inline-flex; align-items: center; border-radius: 99px; padding: 4px 9px;
    font-size: .68rem; font-weight: 800; letter-spacing: .06em; color: #405438; background: #E7EFE1; }
.vc-title { color: #172015; font-size: 1.04rem; line-height: 1.35; font-weight: 800;
    margin: 14px 0 5px; overflow-wrap: anywhere; }
.vc-filename { color: #586353; font-size: .78rem; line-height: 1.4; overflow-wrap: anywhere; }
.vc-meta { color: #52604C; font-size: .8rem; line-height: 1.5; margin-top: 10px; }
.vc-chip { display: inline-block; margin-top: 9px; padding: 4px 10px; border-radius: 99px;
    background: #F0F4EC; border: 1px solid #DFE7D8; color: #405438; font-size: .75rem; font-weight: 700; }
.vc-add-symbol { display: flex; align-items: center; justify-content: center; width: 54px; height: 54px;
    margin: 0 auto 12px; border-radius: 18px; background: rgba(255,255,255,.78);
    border: 1px solid #D6E1CE; color: #536F47; font-size: 2rem; }
.st-key-vault_grid [class*="st-key-vcard_"] button { margin-top: 13px; min-height: 40px; border-radius: 12px !important; }

/* Detail and upload sheets */
.st-key-vault_sheet, .st-key-vault_upload {
    padding: clamp(16px, 2.5vw, 26px); margin: 6px 0 12px;
    border-radius: 23px; border: 1px solid rgba(194,207,185,.95);
    background: rgba(255,255,255,.88); backdrop-filter: blur(14px);
    box-shadow: 0 15px 40px rgba(63,82,53,.105);
}
.vault-sheet-title { color: #111810; font-family: 'Playfair Display', Georgia, serif;
    font-size: 1.55rem; line-height: 1.2; font-weight: 700; overflow-wrap: anywhere; }
.st-key-vault_sheet [data-baseweb="tab-list"] { gap: 5px; }
.st-key-vault_sheet [data-baseweb="tab"] { border-radius: 11px; }
.st-key-vault_sheet [data-testid="stTextArea"] textarea { background: #FBFCF9 !important; color: #172015 !important; }
.st-key-vault_sheet [data-testid="stAlert"], .st-key-vault_upload [data-testid="stAlert"] { border-radius: 13px; }
.st-key-vault_sheet [data-testid="stDownloadButton"] button,
.st-key-vault_sheet [data-testid="stButton"] button,
.st-key-vault_upload [data-testid="stButton"] button { border-radius: 12px !important; }
.st-key-vault_sheet [data-testid="stButton"] button[kind="primary"],
.st-key-vault_upload [data-testid="stButton"] button[kind="primary"] {
    background: #647957 !important; color: white !important; border-color: #647957 !important;
}
.vault-empty { text-align: center; padding: 36px 18px; border-radius: 20px;
    border: 1px dashed #B8C8AE; background: rgba(255,255,255,.54); color: #40503A; }
.vault-empty-icon { font-size: 2.2rem; margin-bottom: 8px; }
.vault-empty-title { color: #1D2819; font-size: 1.15rem; font-weight: 800; margin-bottom: 4px; }
.st-key-vault_page [data-testid="stExpander"] { border: 1px solid #DCE5D5; border-radius: 15px; background: rgba(255,255,255,.55); }
@media (max-width: 760px) {
    .vault-usage { text-align: left; margin-top: 5px; }
    .vault-heading { font-size: 2rem; }
    [class*="st-key-vcard_"] { min-height: 205px; padding: 14px; }
}
/* Vault: unified header and consistent content alignment */
.st-key-vault_page {
    width: 100%;
    max-width: 1180px;
    margin: 0 auto;
    padding: 20px 24px 100px;
}

.st-key-vault_page [data-testid="stHorizontalBlock"] {
    align-items: center;
}

.st-key-vault_page .vault-title {
    line-height: 1.15;
}

/* Empty state: shorter and more balanced */
.vault-empty {
    min-height: 180px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    padding: 24px;
}

/* Document cards should align consistently */
[class*="st-key-vcard_"] {
    box-sizing: border-box;
    min-width: 0;
    min-height: 190px;
    height: 100%;
}

/* Responsive vault */
@media (max-width: 700px) {
    .st-key-vault_page {
        padding: 12px 10px 100px;
    }

    .st-key-vault_page [data-testid="stHorizontalBlock"] {
        gap: 10px !important;
    }

    .st-key-vault_page .vault-title {
        font-size: 30px !important;
        text-align: left;
    }

    [class*="st-key-vcard_"] {
        min-height: 160px;
        padding: 14px;
    }

    .st-key-vault_sheet {
        padding: 14px;
    }
}
</style>
"""


def _fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _fmt_date(timestamp: float) -> str:
    return time.strftime("%d %b %Y", time.localtime(timestamp))


def _flash(message: str) -> None:
    st.session_state["vault_notice"] = message
    st.rerun()


def _setup_card(problem: str) -> None:
    st.warning(problem)
    with st.container(key="vault_sheet"):
        st.markdown('<div class="vault-sheet-title">Set up your vault key</div>', unsafe_allow_html=True)
        st.write(
            "The vault key must be configured once before documents can be stored. "
            "It is separate from the encrypted files and must be backed up securely."
        )
        st.markdown("**1. Generate a key in the VS Code PowerShell terminal:**")
        st.code(
            'python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())',
            language="powershell",
        )
        st.markdown(
            "**2.** Add the generated value as `MINDMATE_VAULT_KEY` in your existing "
            "`.streamlit/secrets.toml` file, above any section headers. Do not share or commit this key."
        )
        st.markdown("**3.** Restart Streamlit. Back up the key somewhere safe; losing it means losing access to the vault files.")


def _preview(user_key: str, doc) -> None:
    try:
        data = store.read_decrypted(user_key, doc.id)
    except store.VaultError as exc:
        st.error(str(exc))
        return

    if doc.ext in att.IMAGE_TYPES:
        st.image(data, caption=doc.title, width="stretch")
        return

    try:
        parsed = att.read_document(doc.original_name, data)
    except att.AttachmentError as exc:
        st.info(f"No text preview is available: {exc} You can still download the original file.")
        return

    if parsed.truncated:
        st.caption("This preview shows only the first part of the document.")
    st.text_area(
        "Document text preview",
        value=parsed.text,
        height=280,
        disabled=True,
        key=f"vault_preview_{doc.id}",
        label_visibility="collapsed",
    )


def _detail(user_key: str, doc) -> None:
    nonce = st.session_state.get("vault_nonce", 0)
    icon = _FILE_STYLE.get(doc.ext, ("FILE", "📄", "file"))[1]

    with st.container(key="vault_sheet"):
        st.markdown(
            f'<div class="vault-sheet-title">{icon} {html_lib.escape(doc.title)}</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"{doc.category}  ·  {doc.original_name}  ·  {_fmt_size(doc.size)}  ·  "
            f"Updated {_fmt_date(doc.updated_at)}"
        )

        tab_preview, tab_edit, tab_replace, tab_more = st.tabs(
            ["Preview", "Rename & category", "Replace file", "Download / delete"]
        )

        with tab_preview:
            _preview(user_key, doc)

        with tab_edit:
            new_title = st.text_input(
                "Document name",
                value=doc.title,
                max_chars=store.MAX_TITLE,
                key=f"vault_rename_{doc.id}",
            )
            categories = store.CATEGORIES
            selected_category = st.selectbox(
                "Category",
                categories,
                index=categories.index(doc.category) if doc.category in categories else len(categories) - 1,
                key=f"vault_category_{doc.id}",
            )
            if st.button("Save changes", key=f"vault_save_edit_{doc.id}", type="primary"):
                if store.rename_document(user_key, doc.id, new_title, selected_category):
                    _flash("Document details updated.")
                else:
                    st.error("Please enter a document name.")

        with tab_replace:
            st.caption("Replace the stored file while keeping this document's ID, title, and category.")
            allowed_types = [ext.lstrip(".") for ext in att.VAULT_TYPES]
            replacement = st.file_uploader(
                "Choose replacement file",
                type=allowed_types,
                key=f"vault_replace_upload_{doc.id}_{nonce}",
            )
            if st.button(
                "Replace encrypted file",
                key=f"vault_replace_btn_{doc.id}",
                type="primary",
                disabled=replacement is None,
            ):
                try:
                    store.replace_document(user_key, doc.id, replacement.name, replacement.getvalue())
                except store.VaultError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["vault_nonce"] = nonce + 1
                    _flash("The file was replaced and encrypted.")

        with tab_more:
            try:
                data = store.read_decrypted(user_key, doc.id)
                st.download_button(
                    "Download decrypted copy",
                    data=data,
                    file_name=doc.original_name,
                    mime=mimetypes.guess_type(doc.original_name)[0] or "application/octet-stream",
                    key=f"vault_download_{doc.id}",
                    width="stretch",
                    on_click=store.log_event,
                    args=(user_key, "download", doc.id, doc.original_name),
                )
                st.caption("The downloaded copy is not encrypted. Store it somewhere safe.")
            except store.VaultError as exc:
                st.error(str(exc))

            st.divider()
            confirm = st.checkbox(
                "I understand this permanently deletes the document",
                key=f"vault_confirm_delete_{doc.id}",
            )
            if st.button(
                "Delete document permanently",
                key=f"vault_delete_{doc.id}",
                disabled=not confirm,
                width="stretch",
            ):
                if store.delete_document(user_key, doc.id):
                    st.session_state["vault_active"] = None
                    _flash("Document deleted.")
                else:
                    st.error("The document could not be deleted. Refresh and try again.")

        if st.button("Close document details", key=f"vault_close_{doc.id}"):
            st.session_state["vault_active"] = None
            st.rerun()


def _upload_box(user_key: str) -> None:
    nonce = st.session_state.get("vault_nonce", 0)
    with st.container(key="vault_upload"):
        st.markdown('<div class="vault-sheet-title">Add to your vault</div>', unsafe_allow_html=True)
        st.caption(
            f"Supported files: PDF, Word, TXT, PNG, JPG and WEBP. "
            f"PDFs up to {att.MAX_PDF_BYTES // (1024 * 1024)} MB; other files up to {store.MAX_FILE_BYTES // (1024 * 1024)} MB. "
            "The file is validated and encrypted before it is stored."
        )
        allowed_types = [ext.lstrip(".") for ext in att.VAULT_TYPES]
        upload = st.file_uploader(
            "Choose a document",
            type=allowed_types,
            key=f"vault_upload_file_{nonce}",
        )
        title = st.text_input(
            "Display name (optional)",
            placeholder="e.g. Annual health report",
            max_chars=store.MAX_TITLE,
            key=f"vault_upload_title_{nonce}",
        )
        category = st.selectbox(
            "Category",
            store.CATEGORIES,
            index=store.CATEGORIES.index(store.DEFAULT_CATEGORY)
            if store.DEFAULT_CATEGORY in store.CATEGORIES
            else len(store.CATEGORIES) - 1,
            key=f"vault_upload_category_{nonce}",
        )

        save_col, cancel_col = st.columns(2)
        if save_col.button(
            "Encrypt and save",
            key="vault_upload_save",
            type="primary",
            width="stretch",
            disabled=upload is None,
        ):
            try:
                doc_id = store.save_document(user_key, upload.name, upload.getvalue(), title, category)
            except store.VaultError as exc:
                st.error(str(exc))
            else:
                st.session_state["vault_nonce"] = nonce + 1
                st.session_state["vault_show_upload"] = False
                st.session_state["vault_active"] = doc_id
                _flash("Document saved and encrypted.")
        if cancel_col.button("Cancel", key="vault_upload_cancel", width="stretch"):
            st.session_state["vault_show_upload"] = False
            st.rerun()


def _document_card(doc) -> None:
    label, icon, css_type = _FILE_STYLE.get(doc.ext, ("FILE", "📄", "file"))
    with st.container(key=f"vcard_{doc.id}"):
        st.markdown(
            f'<div class="vc-top"><span class="vc-icon">{icon}</span>'
            f'<span class="vc-type">{label}</span></div>'
            f'<div class="vc-title">{html_lib.escape(doc.title)}</div>'
            f'<div class="vc-filename">{html_lib.escape(doc.original_name)}</div>'
            f'<div class="vc-meta">{_fmt_size(doc.size)} &nbsp;·&nbsp; {_fmt_date(doc.updated_at)}</div>'
            f'<div class="vc-chip">{html_lib.escape(doc.category)}</div>',
            unsafe_allow_html=True,
        )
        if st.button("Open document", key=f"vault_open_{doc.id}", width="stretch"):
            st.session_state["vault_active"] = doc.id
            st.session_state["vault_show_upload"] = False
            st.rerun()


def _add_card() -> None:
    with st.container(key="vcard_add"):
        st.markdown(
            '<div class="vc-add-symbol">＋</div>'
            '<div class="vc-title">Add more files</div>'
            '<div class="vc-filename">Private, encrypted storage</div>'
            '<div class="vc-meta">PDF · Word · TXT · Images</div>',
            unsafe_allow_html=True,
        )
        if st.button("＋ Add a document", key="vault_add_btn", width="stretch"):
            st.session_state["vault_show_upload"] = not st.session_state.get("vault_show_upload", False)
            st.session_state["vault_active"] = None
            st.rerun()


def render_vault(user_key, name: str, dock) -> None:
    """Entry point called by home.py; preserve the shared account dock."""
    st.markdown(_VAULT_CSS, unsafe_allow_html=True)
    dock(name)

    if not user_key:
        st.error("We could not identify your account. Please log out and sign in again.")
        return

    with st.container(key="vault_page"):
        _page(user_key)


def _page(user_key: str) -> None:
    with st.container(key="vault_header"):
        back_col, title_col, usage_col = st.columns([1.15, 3.7, 1.55], vertical_alignment="center")
        with back_col:
            if st.button("← Dashboard", key="vault_back", width="stretch"):
                st.session_state["view"] = "dashboard"
                st.session_state["vault_active"] = None
                st.session_state["vault_show_upload"] = False
                st.rerun()
        with title_col:
            st.markdown('<div class="vault-heading">Document Vault</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="vault-subheading">A thoughtful home for your important files</div>',
                unsafe_allow_html=True,
            )

        problem = store.key_problem()
        if problem:
            _setup_card(problem)
            return

        count, total = store.usage(user_key)
        with usage_col:
            st.markdown(
                f'<div class="vault-usage">🔒 {count} encrypted file{"s" if count != 1 else ""}'
                f'<br>{_fmt_size(total)} stored</div>',
                unsafe_allow_html=True,
            )

    notice = st.session_state.pop("vault_notice", None)
    if notice:
        st.success(notice)

    with st.container(key="vault_filters"):
        search_col, category_col = st.columns([2.7, 1.1], vertical_alignment="center")
        query = search_col.text_input(
            "Search documents",
            placeholder="⌕  Search by document name or filename",
            label_visibility="collapsed",
            key="vault_query",
            max_chars=100,
        )
        category = category_col.selectbox(
            "Filter by category",
            ["All"] + store.CATEGORIES,
            label_visibility="collapsed",
            key="vault_filter",
        )

    active_id = st.session_state.get("vault_active")
    if active_id:
        doc = store.get_document(user_key, active_id)
        if doc is None:
            st.session_state["vault_active"] = None
        else:
            _detail(user_key, doc)

    if st.session_state.get("vault_show_upload", False):
        _upload_box(user_key)

    docs = store.list_documents(user_key, category, query)
    st.markdown(
        f'<div class="vault-section-title">Your documents <span style="color:#63765A;font-weight:600">'
        f'· {len(docs)} shown</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="vault-helper">Select a file to preview it, edit its details, or download it.</div>',
        unsafe_allow_html=True,
    )

    if not docs and (query or category != "All"):
        st.markdown(
            '<div class="vault-empty"><div class="vault-empty-icon">⌕</div>'
            '<div class="vault-empty-title">No matching documents</div>'
            'Try another search term or category filter.</div>',
            unsafe_allow_html=True,
        )
        # Keep the add-file card available even when filters return no matches.
        cols = st.columns([1, 1, 1], gap="large")
        with cols[0]:
            _add_card()
    elif not docs:
        st.markdown(
            '<div class="vault-empty"><div class="vault-empty-icon">🗂️</div>'
            '<div class="vault-empty-title">Your vault is ready</div>'
            'Add your first document to keep important files in one secure place.</div>',
            unsafe_allow_html=True,
        )
        cols = st.columns([1, 1, 1], gap="large")
        with cols[0]:
            _add_card()
    else:
        cards = list(docs)
        # Three-column grid is intentionally conservative for laptop screens and 8 GB RAM.
        with st.container(key="vault_grid"):
            for start in range(0, len(cards), 3):
                row_cols = st.columns(3, gap="large")
                for col, doc in zip(row_cols, cards[start:start + 3]):
                    with col:
                        _document_card(doc)
            # Put the add card in the next available position.
            if len(cards) % 3:
                remaining = 3 - (len(cards) % 3)
                last_cols = st.columns(3, gap="large")
                with last_cols[0]:
                    _add_card()
            else:
                add_cols = st.columns(3, gap="large")
                with add_cols[0]:
                    _add_card()

    with st.expander("Recent activity", expanded=False):
        events = store.list_events(user_key, 10)
        if not events:
            st.caption("No vault activity yet.")
        else:
            for action, detail, timestamp in events:
                safe_detail = html_lib.escape(str(detail))
                st.caption(
                    f"{time.strftime('%d %b %Y, %H:%M', time.localtime(timestamp))} "
                    f"· {html_lib.escape(str(action).title())} · {safe_detail}"
                )
