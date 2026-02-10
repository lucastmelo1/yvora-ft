# app.py
# Yvora Fichas Técnicas (MVP) - Google Sheets via Google API (sem gspread)
# Tablet-first UI para iPad 10"
#
# Secrets esperados no Streamlit Cloud (TOML):
# SHEET_ID = "..."
# USERS_TAB = "users"
# ITEMS_TAB = "items"
#
# [gcp_service_account]
# type = "service_account"
# project_id = "..."
# private_key_id = "..."
# private_key = """-----BEGIN PRIVATE KEY-----
# ...
# -----END PRIVATE KEY-----"""
# client_email = "..."
# client_id = "..."
# token_uri = "https://oauth2.googleapis.com/token"

import time
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


# =========================
# Page + Tablet UI (Yvora)
# =========================
st.set_page_config(page_title="Yvora | Fichas Técnicas", layout="wide", initial_sidebar_state="collapsed")

YVORA_CREAM = "#EFE7DD"
YVORA_BLUE = "#0E2A47"
YVORA_TEXT = "#1C1C1C"
YVORA_CARD = "#FFFFFF"

st.markdown(
    f"""
<style>
html, body, [class*="css"] {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  color: {YVORA_TEXT};
}}
.stApp {{
  background: {YVORA_CREAM};
}}
.block-container {{
  padding-top: 1.0rem;
  padding-bottom: 1.5rem;
  max-width: 1200px;
}}
.yvora-header {{
  background: {YVORA_BLUE};
  color: white;
  padding: 14px 18px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}}
.yvora-header h1 {{
  font-size: 22px;
  margin: 0;
  font-weight: 750;
}}
.yvora-badge {{
  background: rgba(255,255,255,0.15);
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 14px;
}}
.yvora-card {{
  background: {YVORA_CARD};
  border-radius: 18px;
  padding: 14px 14px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.06);
  border: 1px solid rgba(0,0,0,0.06);
}}
.yvora-muted {{
  color: rgba(0,0,0,0.6);
  font-size: 14px;
}}
.yvora-section-title {{
  font-size: 18px;
  font-weight: 750;
  margin-top: 8px;
}}
.yvora-chip {{
  display: inline-block;
  background: rgba(14,42,71,0.08);
  color: {YVORA_BLUE};
  padding: 6px 10px;
  margin-right: 6px;
  margin-top: 6px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 650;
}}
.stButton > button {{
  border-radius: 14px;
  padding: 12px 14px;
  font-size: 16px;
  font-weight: 650;
  border: 0;
}}
.stButton > button[kind="primary"] {{
  background: {YVORA_BLUE};
}}
.stTextInput input, .stTextArea textarea, .stNumberInput input {{
  border-radius: 12px !important;
  font-size: 16px !important;
}}
#MainMenu {{visibility: hidden;}}
footer {{visibility: hidden;}}
header {{visibility: hidden;}}
</style>
""",
    unsafe_allow_html=True,
)


# =========================
# Config + constants
# =========================
ROLE_LABEL = {"viewer": "Cozinha", "editor": "Chefe", "admin": "Administrador"}
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def can_edit(role: str) -> bool:
    return role in ["editor", "admin"]


def ui_header(auth: Optional[dict] = None):
    badge = "Acesso"
    if auth:
        badge = f"{ROLE_LABEL.get(auth.get('role',''), auth.get('role',''))} | {auth.get('username','')}"
    st.markdown(
        f"""
<div class="yvora-header">
  <h1>Yvora Fichas Técnicas</h1>
  <div class="yvora-badge">{badge}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def card_open():
    st.markdown('<div class="yvora-card">', unsafe_allow_html=True)


def card_close():
    st.markdown("</div>", unsafe_allow_html=True)


# =========================
# Parsing helpers
# =========================
def parse_lines(cell) -> List[str]:
    if cell is None:
        return []
    s = str(cell).strip()
    if not s:
        return []
    return [x.strip() for x in s.split("\n") if x.strip()]


def parse_csv(cell) -> List[str]:
    if cell is None:
        return []
    s = str(cell).strip()
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


def parse_ingredients(cell) -> List[Dict[str, str]]:
    out = []
    for line in parse_lines(cell):
        parts = [p.strip() for p in line.split("|")]
        out.append(
            {
                "item": parts[0] if len(parts) > 0 else "",
                "qty": parts[1] if len(parts) > 1 else "",
                "unit": parts[2] if len(parts) > 2 else "",
            }
        )
    return out


def render_chips(tags: str):
    if not tags:
        return
    for t in [x.strip() for x in str(tags).split(",") if x.strip()]:
        st.markdown(f'<span class="yvora-chip">{t}</span>', unsafe_allow_html=True)


# =========================
# Google Sheets API
# =========================
def require_secret(key: str):
    if key not in st.secrets:
        raise ValueError(f"Secret ausente: {key}")


@st.cache_resource
def get_sheets_service():
    require_secret("gcp_service_account")
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def get_sheet_id() -> str:
    require_secret("SHEET_ID")
    return st.secrets["SHEET_ID"]


def get_tab_names() -> Dict[str, str]:
    users_tab = st.secrets.get("USERS_TAB", "users")
    items_tab = st.secrets.get("ITEMS_TAB", "items")
    return {"users": users_tab, "items": items_tab}


def read_tab_df(tab_name: str) -> pd.DataFrame:
    service = get_sheets_service()
    sheet_id = get_sheet_id()

    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=sheet_id,
            range=tab_name,
            valueRenderOption="UNFORMATTED_VALUE",
            dateTimeRenderOption="FORMATTED_STRING",
        )
        .execute()
    )

    values = result.get("values", [])
    if not values:
        return pd.DataFrame()

    headers = values[0]
    rows = values[1:] if len(values) > 1 else []

    df = pd.DataFrame(rows, columns=headers)
    return df


def write_tab_df(tab_name: str, df: pd.DataFrame):
    """
    Overwrite the whole tab starting at A1.
    """
    service = get_sheets_service()
    sheet_id = get_sheet_id()

    values = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{tab_name}!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()


def df_require_columns(df: pd.DataFrame, cols: List[str], where: str):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Faltando coluna(s) em {where}: {', '.join(missing)}")


def upsert_by_id(df: pd.DataFrame, row: Dict[str, str], key_col: str = "id") -> pd.DataFrame:
    out = df.copy()
    if key_col not in out.columns:
        out[key_col] = ""

    for k in row.keys():
        if k not in out.columns:
            out[k] = ""

    key = str(row.get(key_col, "")).strip()

    if key and key in out[key_col].astype(str).tolist():
        idx = out.index[out[key_col].astype(str) == key][0]
        for k, v in row.items():
            out.at[idx, k] = v
    else:
        out = pd.concat([out, pd.DataFrame([row])], ignore_index=True)

    return out


# =========================
# Auth
# =========================
def do_login(users_df: pd.DataFrame):
    ui_header(None)
    card_open()
    st.markdown("### Login")

    df_require_columns(users_df, ["username", "password", "role", "active"], "aba users")

    u = st.text_input("Usuário", placeholder="ex: cozinha", key="login_user")
    p = st.text_input("Senha", type="password", placeholder="sua senha", key="login_pass")

    colA, colB = st.columns(2)
    with colA:
        enter = st.button("Entrar", type="primary", use_container_width=True)
    with colB:
        st.button("Limpar", use_container_width=True, on_click=lambda: st.session_state.pop("auth", None))

    if enter:
        df = users_df.copy()
        df["active"] = df["active"].astype(str)
        ok = df[
            (df["username"].astype(str).str.strip() == str(u).strip())
            & (df["password"].astype(str) == str(p))
            & (df["active"] == "1")
        ]
        if ok.empty:
            st.error("Usuário ou senha inválidos, ou usuário inativo.")
        else:
            row = ok.iloc[0].to_dict()
            st.session_state["auth"] = {"username": row["username"], "role": row["role"]}
            st.rerun()

    card_close()


def logout_button():
    auth = st.session_state.get("auth")
    if not auth:
        return
    col1, col2, col3 = st.columns([2, 2, 1])
    with col3:
        if st.button("Sair", use_container_width=True):
            st.session_state.pop("auth", None)
            st.session_state.pop("selected_id", None)
            st.session_state.pop("creating_new", None)
            st.rerun()


# =========================
# Render item
# =========================
def item_view(item: dict, mode: str):
    st.markdown(f'<div class="yvora-section-title">{item.get("name","")}</div>', unsafe_allow_html=True)
    meta = f'{item.get("category","")} | {item.get("yield","")} | {item.get("total_time_min","")} min'
    st.markdown(f'<div class="yvora-muted">{meta}</div>', unsafe_allow_html=True)

    cover = item.get("cover_photo_url", "")
    if cover:
        st.image(cover, use_container_width=True)

    render_chips(item.get("tags", ""))

    if mode == "Serviço":
        st.markdown('<div class="yvora-section-title">Ingredientes</div>', unsafe_allow_html=True)
        ing = parse_ingredients(item.get("service_ingredients", ""))
        if ing:
            st.dataframe(pd.DataFrame(ing), use_container_width=True, hide_index=True)
        else:
            st.info("Sem ingredientes cadastrados.")

        st.markdown('<div class="yvora-section-title">Passo a passo</div>', unsafe_allow_html=True)
        steps = parse_lines(item.get("service_steps", ""))
        if steps:
            for i, s in enumerate(steps, 1):
                st.write(f"{i}. {s}")
        else:
            st.info("Sem passos cadastrados.")

        st.markdown('<div class="yvora-section-title">Montagem</div>', unsafe_allow_html=True)
        plating = parse_lines(item.get("service_plating", ""))
        if plating:
            for p in plating:
                st.write(f"- {p}")
        else:
            st.info("Sem montagem cadastrada.")
    else:
        st.markdown('<div class="yvora-section-title">Mise en place</div>', unsafe_allow_html=True)
        mise = parse_lines(item.get("training_mise_en_place", ""))
        if mise:
            for m in mise:
                st.write(f"- {m}")
        else:
            st.info("Sem mise en place cadastrado.")

        st.markdown('<div class="yvora-section-title">Detalhes</div>', unsafe_allow_html=True)
        det = parse_lines(item.get("training_details", ""))
        if det:
            for d in det:
                st.write(f"- {d}")
        else:
            st.info("Sem detalhes cadastrados.")

        st.markdown('<div class="yvora-section-title">Erros comuns</div>', unsafe_allow_html=True)
        err = parse_lines(item.get("training_common_mistakes", ""))
        if err:
            for e in err:
                st.write(f"- {e}")
        else:
            st.info("Sem erros comuns cadastrados.")

        st.markdown('<div class="yvora-section-title">Checklist de qualidade</div>', unsafe_allow_html=True)
        qc = parse_lines(item.get("training_quality_check", ""))
        if qc:
            for q in qc:
                st.write(f"- {q}")
        else:
            st.info("Sem checklist cadastrado.")

        video = item.get("training_video_url", "")
        if video:
            st.link_button("Abrir vídeo", video, use_container_width=True)

        step_photos = parse_csv(item.get("step_photos_urls", ""))
        if step_photos:
            st.markdown('<div class="yvora-section-title">Fotos de etapas</div>', unsafe_allow_html=True)
            for url in step_photos:
                st.image(url, use_container_width=True)


def item_edit(item: dict) -> dict:
    edited = dict(item)

    st.markdown('<div class="yvora-section-title">Editar ficha</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2, 1, 1])
    edited["name"] = c1.text_input("Nome", value=str(item.get("name", "")))
    edited["category"] = c2.text_input("Categoria", value=str(item.get("category", "")))
    edited["total_time_min"] = c3.number_input(
        "Tempo (min)",
        min_value=0,
        value=int(item.get("total_time_min") or 0),
        step=1,
    )

    c4, c5 = st.columns([1, 2])
    edited["yield"] = c4.text_input("Rendimento", value=str(item.get("yield", "")))
    edited["tags"] = c5.text_input("Tags (vírgula)", value=str(item.get("tags", "")))

    edited["cover_photo_url"] = st.text_input("Foto capa (URL Drive)", value=str(item.get("cover_photo_url", "")))
    edited["training_video_url"] = st.text_input("Vídeo treinamento (URL Drive)", value=str(item.get("training_video_url", "")))
    edited["step_photos_urls"] = st.text_area(
        "Fotos etapas (URLs separadas por vírgula)",
        value=str(item.get("step_photos_urls", "")),
        height=80,
    )

    st.markdown('<div class="yvora-section-title">Modo Serviço</div>', unsafe_allow_html=True)
    edited["service_ingredients"] = st.text_area(
        "Ingredientes (1 por linha: item|qty|unit)",
        value=str(item.get("service_ingredients", "")),
        height=160,
    )
    edited["service_steps"] = st.text_area(
        "Passos (1 por linha)",
        value=str(item.get("service_steps", "")),
        height=160,
    )
    edited["service_plating"] = st.text_area(
        "Montagem (1 por linha)",
        value=str(item.get("service_plating", "")),
        height=120,
    )

    st.markdown('<div class="yvora-section-title">Modo Treinamento</div>', unsafe_allow_html=True)
    edited["training_mise_en_place"] = st.text_area(
        "Mise en place (1 por linha)",
        value=str(item.get("training_mise_en_place", "")),
        height=120,
    )
    edited["training_details"] = st.text_area(
        "Detalhes (1 por linha)",
        value=str(item.get("training_details", "")),
        height=120,
    )
    edited["training_common_mistakes"] = st.text_area(
        "Erros comuns (1 por linha)",
        value=str(item.get("training_common_mistakes", "")),
        height=120,
    )
    edited["training_quality_check"] = st.text_area(
        "Checklist qualidade (1 por linha)",
        value=str(item.get("training_quality_check", "")),
        height=120,
    )

    return edited


def render_list_grid(df: pd.DataFrame):
    if df.empty:
        st.info("Nenhum item encontrado.")
        return

    items = df.to_dict(orient="records")
    cols = st.columns(2)

    for i, item in enumerate(items):
        col = cols[i % 2]
        with col:
            card_open()
            cover = item.get("cover_photo_url", "")
            if cover:
                st.image(cover, use_container_width=True)
            st.markdown(f"**{item.get('name','')}**")
            meta = f"{item.get('category','')} | {item.get('total_time_min','')} min"
            st.markdown(f'<div class="yvora-muted">{meta}</div>', unsafe_allow_html=True)

            if st.button("Abrir", key=f"open_{item.get('id','')}", type="primary", use_container_width=True):
                st.session_state["selected_id"] = item.get("id", "")
                st.session_state["creating_new"] = False
                st.rerun()
            card_close()


# =========================
# Main app
# =========================
def show_friendly_error(title: str, detail: str):
    ui_header(st.session_state.get("auth"))
    card_open()
    st.error(title)
    st.write(detail)
    st.write("")
    st.write("Checklist:")
    st.write("1) Secrets com SHEET_ID e gcp_service_account completos")
    st.write("2) Planilha compartilhada com client_email do service account como Editor")
    st.write("3) Abas users e items existem e têm as colunas do template")
    card_close()


def load_data() -> Dict[str, pd.DataFrame]:
    tabs = get_tab_names()
    users_df = read_tab_df(tabs["users"])
    items_df = read_tab_df(tabs["items"])
    return {"users": users_df, "items": items_df, "tabs": tabs}


def run():
    ui_header(st.session_state.get("auth"))
    logout_button()

    try:
        data = load_data()
        users_df = data["users"]
        items_df = data["items"]
        tabs = data["tabs"]
    except Exception as e:
        show_friendly_error("Falha ao acessar Google Sheets", str(e))
        return

    if not st.session_state.get("auth"):
        if users_df.empty:
            show_friendly_error("Aba users vazia", "Importe o template e preencha os usuários.")
            return
        try:
            do_login(users_df)
        except Exception as e:
            show_friendly_error("Erro no login", str(e))
        return

    role = st.session_state["auth"]["role"]

    card_open()
    c1, c2, c3, c4 = st.columns([1, 1, 2, 1])
    with c1:
        module = st.radio("Conteúdo", ["Drinks", "Pratos"])
    with c2:
        mode = st.radio("Modo", ["Serviço", "Treinamento"])
    with c3:
        search = st.text_input("Buscar por nome ou tag", placeholder="ex: gin, pesto, costela")
        category = st.text_input("Filtrar categoria", placeholder="ex: Entrada, Principal, Clássico")
    with c4:
        if can_edit(role):
            if st.button("Novo", type="primary", use_container_width=True):
                prefix = "D" if module == "Drinks" else "P"
                existing = items_df["id"].astype(str).tolist() if "id" in items_df.columns else []
                new_id = f"{prefix}{str(len(existing) + 1).zfill(3)}"
                st.session_state["selected_id"] = new_id
                st.session_state["creating_new"] = True
                st.rerun()
        else:
            st.button("Novo", disabled=True, use_container_width=True)
    card_close()

    module_type = "drink" if module == "Drinks" else "prato"

    try:
        if items_df.empty:
            df = pd.DataFrame(columns=["id", "type", "name"])
        else:
            df_require_columns(items_df, ["id", "type", "name"], "aba items")
            df = items_df.copy()
            df["type"] = df["type"].astype(str).str.lower().str.strip()
            df["name"] = df["name"].astype(str)

            df = df[df["type"] == module_type]

            if search:
                s = search.strip().lower()
                tags_col = df["tags"].astype(str) if "tags" in df.columns else ""
                df = df[df["name"].str.lower().str.contains(s) | tags_col.str.lower().str.contains(s)]

            if category:
                c = category.strip().lower()
                cat_col = df["category"].astype(str) if "category" in df.columns else ""
                df = df[cat_col.str.lower().str.contains(c)]

            df = df.sort_values("name")
    except Exception as e:
        show_friendly_error("Estrutura da aba items inválida", str(e))
        return

    left, right = st.columns([1, 1])

    with left:
        st.markdown('<div class="yvora-section-title">Lista</div>', unsafe_allow_html=True)
        render_list_grid(df)

    with right:
        selected_id = st.session_state.get("selected_id", "")
        creating_new = st.session_state.get("creating_new", False)

        st.markdown('<div class="yvora-section-title">Ficha</div>', unsafe_allow_html=True)

        if not selected_id:
            st.info("Selecione um item na lista.")
            return

        if creating_new:
            if not can_edit(role):
                st.error("Sem permissão para criar.")
                return

            base = {
                "id": selected_id,
                "type": module_type,
                "name": "",
                "category": "",
                "tags": "",
                "yield": "",
                "total_time_min": "0",
                "cover_photo_url": "",
                "training_video_url": "",
                "step_photos_urls": "",
                "service_ingredients": "",
                "service_steps": "",
                "service_plating": "",
                "training_mise_en_place": "",
                "training_details": "",
                "training_common_mistakes": "",
                "training_quality_check": "",
            }

            card_open()
            edited = item_edit(base)

            colS, colC = st.columns(2)
            with colS:
                if st.button("Salvar", type="primary", use_container_width=True):
                    try:
                        new_items = upsert_by_id(items_df if not items_df.empty else pd.DataFrame(), edited, "id")
                        write_tab_df(tabs["items"], new_items)
                        st.session_state["creating_new"] = False
                        st.success("Item criado.")
                        time.sleep(0.4)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Falha ao salvar: {e}")
            with colC:
                if st.button("Cancelar", use_container_width=True):
                    st.session_state["creating_new"] = False
                    st.session_state["selected_id"] = ""
                    st.rerun()
            card_close()
            return

        match = items_df[items_df["id"].astype(str) == str(selected_id)] if not items_df.empty else pd.DataFrame()
        if match.empty:
            st.warning("Item não encontrado. Atualize a lista ou recrie.")
            return

        item = match.iloc[0].to_dict()

        card_open()
        item_view(item, mode)
        card_close()

        if can_edit(role):
            st.write("")
            card_open()
            with st.expander("Editar esta ficha", expanded=False):
                edited = item_edit(item)
                if st.button("Salvar alterações", type="primary", use_container_width=True):
                    try:
                        new_items = upsert_by_id(items_df, edited, "id")
                        write_tab_df(tabs["items"], new_items)
                        st.success("Alterações salvas.")
                        time.sleep(0.4)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Falha ao salvar: {e}")
            card_close()


try:
    run()
except Exception as e:
    show_friendly_error("Erro inesperado no app", str(e))
