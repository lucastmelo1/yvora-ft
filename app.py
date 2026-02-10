import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import time
from pathlib import Path

# ======================================================
# CONFIG GERAL
# ======================================================
st.set_page_config(
    page_title="Yvora | Fichas Técnicas",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ======================================================
# ESTILO YVORA (iPad 10")
# ======================================================
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial;
}
.stApp {
    background-color: #EFE7DD;
}
.block-container {
    max-width: 1200px;
    padding-top: 1rem;
}
.card {
    background: white;
    border-radius: 18px;
    padding: 16px;
    margin-bottom: 16px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.06);
}
.title-bar {
    background: #0E2A47;
    color: white;
    padding: 14px 18px;
    border-radius: 18px;
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.title-left {
    display: flex;
    align-items: center;
    gap: 12px;
}
.title-bar h1 {
    font-size: 20px;
    margin: 0;
}
.badge {
    background: rgba(255,255,255,0.15);
    padding: 8px 14px;
    border-radius: 999px;
    font-size: 14px;
    display: flex;
    gap: 10px;
    align-items: center;
}
.stButton > button {
    border-radius: 14px;
    font-size: 16px;
    padding: 12px;
}
.stButton > button[kind="primary"] {
    background-color: #0E2A47;
}
.small-btn > button {
    padding: 8px 10px !important;
    font-size: 14px !important;
    border-radius: 12px !important;
}
</style>
""", unsafe_allow_html=True)

# ======================================================
# LOGO (na raiz do repo)
# ======================================================
# Esperado: arquivo na raiz do repo com nome "Ivora_logo" e extensão (.png/.jpg/.jpeg/.webp)
LOGO_BASENAME = "Ivora_logo"
LOGO_EXTS = [".png", ".jpg", ".jpeg", ".webp"]

def find_logo_path() -> str | None:
    base = Path(__file__).parent  # raiz onde está o app.py
    for ext in LOGO_EXTS:
        p = base / f"{LOGO_BASENAME}{ext}"
        if p.exists():
            return str(p)
    return None

# ======================================================
# GOOGLE SHEETS
# ======================================================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

@st.cache_resource
def get_service():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)

def read_sheet(tab):
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=st.secrets["SHEET_ID"],
        range=tab
    ).execute()

    values = result.get("values", [])
    if not values:
        return pd.DataFrame()

    return pd.DataFrame(values[1:], columns=values[0])

def write_sheet(tab, df):
    service = get_service()
    values = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
    service.spreadsheets().values().update(
        spreadsheetId=st.secrets["SHEET_ID"],
        range=f"{tab}!A1",
        valueInputOption="RAW",
        body={"values": values}
    ).execute()

# ======================================================
# AUTH
# ======================================================
ROLE_LABEL = {"viewer":"Cozinha","editor":"Chefe","admin":"Administrador"}

def logout():
    st.session_state.pop("auth", None)
    st.session_state.pop("item", None)
    st.session_state.pop("selected_id", None)
    st.session_state.pop("creating_new", None)
    st.session_state.pop("login_user", None)
    st.session_state.pop("login_pass", None)

def can_edit():
    return st.session_state.get("auth", {}).get("role") in ["admin", "editor"]

def login(users):
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Login")

    u = st.text_input("Usuário", key="login_user")
    p = st.text_input("Senha", type="password", key="login_pass")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Entrar", type="primary", use_container_width=True):
            match = users[
                (users["username"].astype(str) == str(u)) &
                (users["password"].astype(str) == str(p)) &
                (users["active"].astype(str) == "1")
            ]
            if match.empty:
                st.error("Usuário ou senha inválidos (ou usuário inativo).")
            else:
                row = match.iloc[0]
                st.session_state["auth"] = {
                    "username": str(row["username"]),
                    "role": str(row["role"])
                }
                st.session_state.pop("item", None)
                st.rerun()
    with col2:
        if st.button("Limpar", use_container_width=True):
            st.session_state["login_user"] = ""
            st.session_state["login_pass"] = ""

    st.markdown("</div>", unsafe_allow_html=True)

# ======================================================
# HEADER (com logo na raiz + botão trocar usuário)
# ======================================================
def header():
    auth = st.session_state.get("auth")
    user_text = "Acesso"
    if auth:
        user_text = f"{ROLE_LABEL.get(auth.get('role',''), auth.get('role',''))} | {auth.get('username','')}"

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

    # Logo diretamente na raiz do repo
    lp = find_logo_path()
    if lp:
        colA, colB = st.columns([1, 3])
        with colA:
            st.image(lp, use_container_width=True)

    # Botão para trocar usuário
    if auth:
        col1, col2, col3 = st.columns([2, 2, 2])
        with col3:
            st.markdown('<div class="small-btn">', unsafe_allow_html=True)
            if st.button("Trocar usuário", use_container_width=True):
                logout()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

# ======================================================
# APP PRINCIPAL
# ======================================================
def main():
    header()

    users_tab = st.secrets.get("USERS_TAB", "users")
    items_tab = st.secrets.get("ITEMS_TAB", "items")

    users = read_sheet(users_tab)
    items = read_sheet(items_tab)

    if "auth" not in st.session_state:
        login(users)
        return

    # Seletores principais
    colA, colB, colC = st.columns([1, 1, 2])
    with colA:
        tipo = st.radio("Conteúdo", ["Drinks", "Pratos"])
    with colB:
        modo = st.radio("Modo", ["Serviço", "Treinamento"])
    with colC:
        busca = st.text_input("Buscar", placeholder="nome / tag")

    tipo_val = "drink" if tipo == "Drinks" else "prato"

    if not items.empty:
        df = items[items["type"].astype(str).str.lower() == tipo_val].copy()
    else:
        df = pd.DataFrame(columns=["id", "type", "name"])

    if busca and not df.empty:
        b = busca.strip().lower()
        tags = df["tags"].astype(str) if "tags" in df.columns else ""
        df = df[df["name"].astype(str).str.lower().str.contains(b) | tags.str.lower().str.contains(b)]

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
        st.warning("Item não encontrado na base.")
        return

    item = match.iloc[0].to_dict()

    # Visualização do item
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader(str(item.get("name","")))

    cover = str(item.get("cover_photo_url","")).strip()
    if cover:
        st.image(cover, use_container_width=True)

    st.caption(f"{item.get('category','')} · {item.get('yield','')} · {item.get('total_time_min','')} min")

    if modo == "Serviço":
        st.markdown("### Ingredientes")
        st.text(str(item.get("service_ingredients","")))

        st.markdown("### Preparo")
        st.text(str(item.get("service_steps","")))

        st.markdown("### Montagem")
        st.text(str(item.get("service_plating","")))
    else:
        st.markdown("### Mise en place")
        st.text(str(item.get("training_mise_en_place","")))

        st.markdown("### Detalhes")
        st.text(str(item.get("training_details","")))

        st.markdown("### Erros comuns")
        st.text(str(item.get("training_common_mistakes","")))

        video = str(item.get("training_video_url","")).strip()
        if video:
            st.link_button("Assistir vídeo", video, use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # Edição (chefe/admin)
    if can_edit():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Editar ficha (Chefe/Admin)")

        edited = dict(item)

        edited["cover_photo_url"] = st.text_input("Foto capa (URL)", value=str(item.get("cover_photo_url","")))
        edited["training_video_url"] = st.text_input("Vídeo (URL)", value=str(item.get("training_video_url","")))

        edited["service_ingredients"] = st.text_area("Ingredientes (Serviço)", value=str(item.get("service_ingredients","")), height=140)
        edited["service_steps"] = st.text_area("Passos (Serviço)", value=str(item.get("service_steps","")), height=140)
        edited["service_plating"] = st.text_area("Montagem", value=str(item.get("service_plating","")), height=120)

        edited["training_mise_en_place"] = st.text_area("Mise en place (Treinamento)", value=str(item.get("training_mise_en_place","")), height=120)
        edited["training_details"] = st.text_area("Detalhes (Treinamento)", value=str(item.get("training_details","")), height=120)
        edited["training_common_mistakes"] = st.text_area("Erros comuns (Treinamento)", value=str(item.get("training_common_mistakes","")), height=120)

        if st.button("Salvar alterações", type="primary", use_container_width=True):
            for k, v in edited.items():
                items.loc[items["id"].astype(str) == str(edited["id"]), k] = str(v)

            write_sheet(items_tab, items)
            st.success("Alterações salvas.")
            time.sleep(0.4)
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

# ======================================================
# START
# ======================================================
main()
