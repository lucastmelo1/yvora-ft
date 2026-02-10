import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
import streamlit as st
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import AuthorizedSession

# =========================
# CONFIG
# =========================
st.set_page_config(
    page_title="Yvora | Fichas Técnicas",
    layout="wide",
    initial_sidebar_state="collapsed"
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
ROLE_LABEL = {"viewer": "Cozinha", "editor": "Chefe", "admin": "Administrador"}

LOGO_BASENAME = "Ivora_logo"
LOGO_EXTS = [".png", ".jpg", ".jpeg", ".webp"]

# =========================
# STYLE
# =========================
st.markdown(
    """
<style>
html, body, [class*="css"] { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial; }
.stApp { background-color: #EFE7DD; }
.block-container { max-width: 1200px; padding-top: 1rem; }

.card {
    background: #FFFFFF;
    border-radius: 18px;
    padding: 16px;
    margin-bottom: 16px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.06);
    border: 1px solid rgba(0,0,0,0.06);
}

.title-bar {
    background: #0E2A47;
    color: white;
    padding: 14px 18px;
    border-radius: 18px;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.title-left { display: flex; align-items: center; gap: 12px; }
.title-bar h1 { font-size: 20px; margin: 0; }

.badge {
    background: rgba(255,255,255,0.15);
    padding: 8px 14px;
    border-radius: 999px;
    font-size: 14px;
    display: flex;
    gap: 10px;
    align-items: center;
}

.small-btn > button {
    padding: 8px 10px !important;
    font-size: 14px !important;
    border-radius: 12px !important;
}

.stButton > button {
    border-radius: 14px;
    font-size: 16px;
    padding: 12px;
}

.stButton > button[kind="primary"] { background-color: #0E2A47; }
</style>
""",
    unsafe_allow_html=True
)

# =========================
# LOGO (root)
# =========================
def find_logo_path() -> Optional[str]:
    base = Path(__file__).parent
    for ext in LOGO_EXTS:
        p = base / f"{LOGO_BASENAME}{ext}"
        if p.exists():
            return str(p)
    return None

# =========================
# SESSION / AUTH
# =========================
def logout():
    st.session_state.pop("auth", None)
    st.session_state.pop("item", None)
    st.session_state.pop("login_user", None)
    st.session_state.pop("login_pass", None)

def can_edit() -> bool:
    return st.session_state.get("auth", {}).get("role") in ["admin", "editor"]

def to_bool01(x) -> bool:
    # aceita 1, "1", True, "true", etc
    if x is None:
        return False
    s = str(x).strip().lower()
    return s in ["1", "true", "yes", "y", "sim"]

# =========================
# GOOGLE SHEETS (REST)
# =========================
@st.cache_resource
def get_authed_session() -> AuthorizedSession:
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    return AuthorizedSession(creds)

def sheet_id() -> str:
    return st.secrets["SHEET_ID"]

def tab_users() -> str:
    return st.secrets.get("USERS_TAB", "users")

def tab_items() -> str:
    return st.secrets.get("ITEMS_TAB", "items")

def _request_json(method: str, url: str, **kwargs) -> dict:
    sess = get_authed_session()
    last_err = None
    for attempt in range(4):
        try:
            resp = sess.request(method, url, timeout=30, **kwargs)
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
            return resp.json()
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))
        except Exception as e:
            last_err = e
            break
    raise RuntimeError(f"Falha de rede ao acessar Google Sheets: {last_err}")

def read_sheet(tab: str) -> pd.DataFrame:
    rng = requests.utils.quote(tab, safe="!:'()[],.-_ ")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id()}/values/{rng}?valueRenderOption=UNFORMATTED_VALUE"
    data = _request_json("GET", url)
    values = data.get("values", [])
    if not values:
        return pd.DataFrame()
    headers = values[0]
    rows = values[1:] if len(values) > 1 else []
    return pd.DataFrame(rows, columns=headers)

def write_sheet(tab: str, df: pd.DataFrame):
    rng = requests.utils.quote(f"{tab}!A1", safe="!:'()[],.-_ ")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id()}/values/{rng}?valueInputOption=RAW"
    values = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
    _request_json("PUT", url, json={"values": values})

# =========================
# UI PIECES
# =========================
def header():
    auth = st.session_state.get("auth")
    user_text = "Acesso"
    if auth:
        # Mostra username e permissões (opcional)
        perm = []
        if auth.get("can_drinks"):
            perm.append("drinks")
        if auth.get("can_pratos"):
            perm.append("pratos")
        perm_txt = ", ".join(perm) if perm else "sem acesso"
        user_text = f"{auth.get('username','')} | {perm_txt}"

    st.markdown(
        f"""
        <div class="title-bar">
            <div class="title-left">
                <h1>Yvora · Fichas Técnicas</h1>
            </div>
            <div class="badge">
                <span>{user_text}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    lp = find_logo_path()
    if lp:
        colA, colB = st.columns([1, 3])
        with colA:
            st.image(lp, use_container_width=True)

    if auth:
        c1, c2, c3 = st.columns([2, 2, 2])
        with c3:
            st.markdown('<div class="small-btn">', unsafe_allow_html=True)
            if st.button("Trocar usuário", use_container_width=True):
                logout()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

def login_screen(users_df: pd.DataFrame):
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Login")

    u = st.text_input("Usuário", key="login_user")
    p = st.text_input("Senha", type="password", key="login_pass")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Entrar", type="primary", use_container_width=True):
            required = ["username", "password", "role", "active", "can_drinks", "can_pratos"]
            for c in required:
                if c not in users_df.columns:
                    st.error(f"Faltando coluna na aba users: {c}")
                    st.markdown("</div>", unsafe_allow_html=True)
                    return

            df = users_df.copy()
            for c in required:
                df[c] = df[c].astype(str)

            match = df[
                (df["username"] == str(u)) &
                (df["password"] == str(p)) &
                (df["active"] == "1")
            ]

            if match.empty:
                st.error("Usuário ou senha inválidos (ou usuário inativo).")
            else:
                row = match.iloc[0]
                can_drinks = to_bool01(row["can_drinks"])
                can_pratos = to_bool01(row["can_pratos"])

                if not (can_drinks or can_pratos):
                    st.error("Usuário ativo, mas sem permissão para Drinks nem Pratos.")
                    st.markdown("</div>", unsafe_allow_html=True)
                    return

                st.session_state["auth"] = {
                    "username": str(row["username"]),
                    "role": str(row["role"]),
                    "can_drinks": can_drinks,
                    "can_pratos": can_pratos,
                }
                st.session_state.pop("item", None)
                st.rerun()
    with col2:
        if st.button("Limpar", use_container_width=True):
            st.session_state["login_user"] = ""
            st.session_state["login_pass"] = ""

    st.markdown("</div>", unsafe_allow_html=True)

def allowed_content_options() -> list[str]:
    auth = st.session_state["auth"]
    opts = []
    if auth.get("can_drinks"):
        opts.append("Drinks")
    if auth.get("can_pratos"):
        opts.append("Pratos")
    return opts

# =========================
# MAIN
# =========================
def main():
    header()

    try:
        users = read_sheet(tab_users())
        items = read_sheet(tab_items())
    except Exception as e:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.error("Falha ao carregar dados do Google Sheet.")
        st.write(str(e))
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if "auth" not in st.session_state:
        login_screen(users)
        return

    # --- Conteúdo permitido por usuário
    options = allowed_content_options()
    if not options:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.error("Usuário sem permissão configurada (can_drinks/can_pratos).")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Define default estável: se já tem seleção, respeita, senão usa a 1a opção permitida
    if "content_choice" not in st.session_state or st.session_state["content_choice"] not in options:
        st.session_state["content_choice"] = options[0]

    colA, colB, colC = st.columns([1, 1, 2])
    with colA:
        tipo = st.radio("Conteúdo", options, key="content_choice")
    with colB:
        modo = st.radio("Modo", ["Serviço", "Treinamento"])
    with colC:
        busca = st.text_input("Buscar", placeholder="nome / tag")

    tipo_val = "drink" if tipo == "Drinks" else "prato"

    # Filtra items
    if items.empty:
        df = pd.DataFrame(columns=["id", "type", "name"])
    else:
        for c in ["id", "type", "name"]:
            if c not in items.columns:
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.error(f"Faltando coluna na aba items: {c}")
                st.markdown("</div>", unsafe_allow_html=True)
                return

        df = items.copy()
        df["type"] = df["type"].astype(str).str.lower()
        df["name"] = df["name"].astype(str)

        df = df[df["type"] == tipo_val]

        if busca:
            b = busca.strip().lower()
            tags = df["tags"].astype(str) if "tags" in df.columns else ""
            df = df[df["name"].str.lower().str.contains(b) | tags.str.lower().str.contains(b)]

    # Lista
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Itens")
    if df.empty:
        st.info("Nenhum item encontrado.")
    else:
        for _, row in df.sort_values("name").iterrows():
            if st.button(str(row["name"]), use_container_width=True, key=f"btn_{row['id']}"):
                st.session_state["item"] = str(row["id"])
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if "item" not in st.session_state:
        return

    match = items[items["id"].astype(str) == str(st.session_state["item"])]
    if match.empty:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.warning("Item não encontrado na base.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    item = match.iloc[0].to_dict()

    # Proteção extra: se o item selecionado não for do tipo permitido, limpa
    if str(item.get("type", "")).strip().lower() != tipo_val:
        st.session_state.pop("item", None)
        st.rerun()

    # Visualização
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader(str(item.get("name", "")))

    cover = str(item.get("cover_photo_url", "")).strip()
    if cover:
        st.image(cover, use_container_width=True)

    st.caption(f"{item.get('category','')} · {item.get('yield','')} · {item.get('total_time_min','')} min")

    if modo == "Serviço":
        st.markdown("### Ingredientes")
        st.text(str(item.get("service_ingredients", "")))

        st.markdown("### Preparo")
        st.text(str(item.get("service_steps", "")))

        st.markdown("### Montagem")
        st.text(str(item.get("service_plating", "")))
    else:
        st.markdown("### Mise en place")
        st.text(str(item.get("training_mise_en_place", "")))

        st.markdown("### Detalhes")
        st.text(str(item.get("training_details", "")))

        st.markdown("### Erros comuns")
        st.text(str(item.get("training_common_mistakes", "")))

        video = str(item.get("training_video_url", "")).strip()
        if video:
            st.link_button("Assistir vídeo", video, use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # Edição
    if can_edit():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Editar ficha (Chefe/Admin)")

        edited = dict(item)

        edited["cover_photo_url"] = st.text_input("Foto capa (URL)", value=str(item.get("cover_photo_url", "")))
        edited["training_video_url"] = st.text_input("Vídeo (URL)", value=str(item.get("training_video_url", "")))

        edited["service_ingredients"] = st.text_area("Ingredientes (Serviço)", value=str(item.get("service_ingredients", "")), height=140)
        edited["service_steps"] = st.text_area("Passos (Serviço)", value=str(item.get("service_steps", "")), height=140)
        edited["service_plating"] = st.text_area("Montagem", value=str(item.get("service_plating", "")), height=120)

        edited["training_mise_en_place"] = st.text_area("Mise en place (Treinamento)", value=str(item.get("training_mise_en_place", "")), height=120)
        edited["training_details"] = st.text_area("Detalhes (Treinamento)", value=str(item.get("training_details", "")), height=120)
        edited["training_common_mistakes"] = st.text_area("Erros comuns (Treinamento)", value=str(item.get("training_common_mistakes", "")), height=120)

        if st.button("Salvar alterações", type="primary", use_container_width=True):
            for k, v in edited.items():
                items.loc[items["id"].astype(str) == str(edited["id"]), k] = str(v)

            try:
                write_sheet(tab_items(), items)
            except Exception as e:
                st.error(f"Falha ao salvar no Google Sheet: {e}")
                st.markdown("</div>", unsafe_allow_html=True)
                return

            st.success("Alterações salvas.")
            time.sleep(0.4)
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


main()
