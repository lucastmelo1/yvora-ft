import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import time

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
    padding: 16px 20px;
    border-radius: 18px;
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.title-bar h1 {
    font-size: 22px;
    margin: 0;
}
.badge {
    background: rgba(255,255,255,0.15);
    padding: 8px 14px;
    border-radius: 999px;
    font-size: 14px;
}
.stButton > button {
    border-radius: 14px;
    font-size: 16px;
    padding: 12px;
}
.stButton > button[kind="primary"] {
    background-color: #0E2A47;
}
</style>
""", unsafe_allow_html=True)

# ======================================================
# GOOGLE SHEETS
# ======================================================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

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
def login(users):
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Login")

    u = st.text_input("Usuário")
    p = st.text_input("Senha", type="password")

    if st.button("Entrar", type="primary", use_container_width=True):
        match = users[
            (users["username"] == u) &
            (users["password"] == p) &
            (users["active"] == "1")
        ]
        if match.empty:
            st.error("Usuário ou senha inválidos")
        else:
            row = match.iloc[0]
            st.session_state["auth"] = {
                "username": row["username"],
                "role": row["role"]
            }
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

def can_edit():
    return st.session_state["auth"]["role"] in ["admin", "editor"]

# ======================================================
# APP
# ======================================================
def main():
    st.markdown(
        f"""
        <div class="title-bar">
            <h1>Yvora · Fichas Técnicas</h1>
            <div class="badge">{st.session_state.get("auth", {}).get("username","")}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    users = read_sheet(st.secrets["USERS_TAB"])
    items = read_sheet(st.secrets["ITEMS_TAB"])

    if "auth" not in st.session_state:
        login(users)
        return

    colA, colB = st.columns([1,1])
    with colA:
        tipo = st.radio("Conteúdo", ["Drinks", "Pratos"])
    with colB:
        modo = st.radio("Modo", ["Serviço", "Treinamento"])

    tipo_val = "drink" if tipo == "Drinks" else "prato"
    df = items[items["type"] == tipo_val]

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Itens")

    for _, row in df.iterrows():
        if st.button(row["name"], use_container_width=True):
            st.session_state["item"] = row["id"]
    st.markdown("</div>", unsafe_allow_html=True)

    if "item" not in st.session_state:
        return

    item = items[items["id"] == st.session_state["item"]].iloc[0]

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader(item["name"])

    if item.get("cover_photo_url"):
        st.image(item["cover_photo_url"], use_container_width=True)

    if modo == "Serviço":
        st.markdown("### Ingredientes")
        st.text(item.get("service_ingredients",""))

        st.markdown("### Preparo")
        st.text(item.get("service_steps",""))

        st.markdown("### Montagem")
        st.text(item.get("service_plating",""))
    else:
        st.markdown("### Mise en place")
        st.text(item.get("training_mise_en_place",""))

        st.markdown("### Detalhes")
        st.text(item.get("training_details",""))

        st.markdown("### Erros comuns")
        st.text(item.get("training_common_mistakes",""))

        if item.get("training_video_url"):
            st.link_button("Assistir vídeo", item["training_video_url"])

    st.markdown("</div>", unsafe_allow_html=True)

    if can_edit():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Editar ficha")

        edited = dict(item)
        edited["service_ingredients"] = st.text_area(
            "Ingredientes (Serviço)", item.get("service_ingredients","")
        )
        edited["service_steps"] = st.text_area(
            "Passos (Serviço)", item.get("service_steps","")
        )
        edited["service_plating"] = st.text_area(
            "Montagem", item.get("service_plating","")
        )

        if st.button("Salvar alterações", type="primary"):
            items.loc[items["id"] == edited["id"]] = pd.Series(edited)
            write_sheet(st.secrets["ITEMS_TAB"], items)
            st.success("Salvo com sucesso")
            time.sleep(0.5)
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

# ======================================================
# START
# ======================================================
main()
