import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="Yvora Fichas Técnicas",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =========================
# YVORA TABLET UI (iPad 10")
# =========================
YVORA_CREAM = "#EFE7DD"
YVORA_BLUE = "#0E2A47"
YVORA_TEXT = "#1C1C1C"
YVORA_CARD = "#FFFFFF"

st.markdown(
    f"""
<style>
/* Base */
html, body, [class*="css"] {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  color: {YVORA_TEXT};
}}
.stApp {{
  background: {YVORA_CREAM};
}}

/* Remove some default spacing for tablet */
.block-container {{
  padding-top: 1.0rem;
  padding-bottom: 1.5rem;
  max-width: 1200px;
}}

/* Title bar */
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
  font-weight: 700;
}}
.yvora-badge {{
  background: rgba(255,255,255,0.15);
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 14px;
}}

/* Big touch buttons */
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
.stButton > button:hover {{
  filter: brightness(0.98);
}}

/* Cards */
.yvora-card {{
  background: {YVORA_CARD};
  border-radius: 18px;
  padding: 14px 14px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.06);
  border: 1px solid rgba(0,0,0,0.06);
}}
.yvora-card h2 {{
  font-size: 18px;
  margin: 0 0 6px 0;
}}
.yvora-muted {{
  color: rgba(0,0,0,0.6);
  font-size: 14px;
}}
.yvora-section-title {{
  font-size: 18px;
  font-weight: 750;
  margin-top: 10px;
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

/* Inputs bigger */
.stTextInput input, .stTextArea textarea, .stNumberInput input {{
  border-radius: 12px !important;
  font-size: 16px !important;
}}
.stRadio label, .stRadio div {{
  font-size: 16px !important;
}}

/* Hide Streamlit default menu/footer for kiosk feel */
#MainMenu {{visibility: hidden;}}
footer {{visibility: hidden;}}
header {{visibility: hidden;}}
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# CONFIG (Secrets)
# =========================
def get_secret(key: str, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

SHEET_ID = get_secret("SHEET_ID", "")
USERS_TAB = get_secret("USERS_TAB", "users")
ITEMS_TAB = get_secret("ITEMS_TAB", "items")

ROLE_LABEL = {
    "viewer": "Cozinha",
    "editor": "Chefe",
    "admin": "Administrador",
}

def can_edit(role: str) -> bool:
    return role in ["editor", "admin"]

# =========================
# HELPERS
# =========================
def parse_lines(cell) -> list[str]:
    if cell is None:
        return []
    s = str(cell).strip()
    if not s:
        return []
    return [x.strip() for x in s.split("\n") if x.strip()]

def parse_csv(cell) -> list[str]:
    if cell is None:
        return []
    s = str(cell).strip()
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]

def parse_ingredients(cell) -> list[dict]:
    rows = []
    for line in parse_lines(cell):
        parts = [p.strip() for p in line.split("|")]
        item = parts[0] if len(parts) > 0 else ""
        qty = parts[1] if len(parts) > 1 else ""
        unit = parts[2] if len(parts) > 2 else ""
        rows.append({"item": item, "qty": qty, "unit": unit})
    return rows

def df_require_columns(df: pd.DataFrame, cols: list[str], where: str):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Faltando coluna(s) em {where}: {', '.join(missing)}")

def ui_header(auth=None):
    role_badge = ""
    if auth:
        role_badge = f'{ROLE_LABEL.get(auth.get("role",""), auth.get("role",""))} | {auth.get("username","")}'
    else:
        role_badge = "Acesso"
    st.markdown(
        f"""
<div class="yvora-header">
  <h1>Yvora Fichas Técnicas</h1>
  <div class="yvora-badge">{role_badge}</div>
</div>
""",
        unsafe_allow_html=True,
    )

def ui_card_open():
    st.markdown('<div class="yvora-card">', unsafe_allow_html=True)

def ui_card_close():
    st.markdown("</div>", unsafe_allow_html=True)

def show_friendly_error(title: str, detail: str):
    ui_header(st.session_state.get("auth"))
    ui_card_open()
    st.error(title)
    st.write(detail)
    st.write("")
    st.write("Checklist rápido:")
    st.write("1) Secrets com SHEET_ID e gcp_service_account completos")
    st.write("2) Planilha compartilhada com o client_email do service account como Editor")
    st.write("3) Abas users e items existem e têm as colunas do template")
    ui_card_close()

# =========================
# GOOGLE SHEETS
# =========================
@st.cache_resource
def get_gspread_client():
    sa_info = st.secrets["gcp_service_account"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
    return gspread.authorize(creds)

def open_sheet():
    if not SHEET_ID:
        raise ValueError("SHEET_ID não configurado nos Secrets.")
    client = get_gspread_client()
    return client.open_by_key(SHEET_ID)

def read_tab_df(sh, tab_name: str) -> pd.DataFrame:
    try:
        ws = sh.worksheet(tab_name)
    except Exception as e:
        raise ValueError(f"Aba '{tab_name}' não encontrada. Crie a aba com esse nome. Detalhe: {e}")
    data = ws.get_all_records()
    return pd.DataFrame(data)

def write_tab_df(sh, tab_name: str, df: pd.DataFrame):
    ws = sh.worksheet(tab_name)
    ws.clear()
    ws.update([df.columns.tolist()] + df.fillna("").astype(str).values.tolist())

def upsert_row(df: pd.DataFrame, key_col: str, row: dict) -> pd.DataFrame:
    out = df.copy()
    if key_col not in out.columns:
        out[key_col] = ""
    if str(row.get(key_col, "")) in out[key_col].astype(str).tolist():
        idx = out.index[out[key_col].astype(str) == str(row.get(key_col, ""))][0]
        for k, v in row.items():
            if k not in out.columns:
                out[k] = ""
            out.at[idx, k] = v
    else:
        for k in row.keys():
            if k not in out.columns:
                out[k] = ""
        out = pd.concat([out, pd.DataFrame([row])], ignore_index=True)
    return out

# =========================
# AUTH
# =========================
def do_login(users_df: pd.DataFrame):
    ui_header(None)
    ui_card_open()
    st.markdown("### Login")

    u = st.text_input("Usuário", placeholder="ex: cozinha")
    p = st.text_input("Senha", type="password", placeholder="sua senha")

    colA, colB = st.columns([1, 1])
    with colA:
        entrar = st.button("Entrar", type="primary", use_container_width=True)
    with colB:
        st.button("Limpar", use_container_width=True, on_click=lambda: st.session_state.pop("auth", None))

    if entrar:
        df_require_columns(users_df, ["username", "password", "role", "active"], "aba users")
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

    ui_card_close()

def logout_area():
    auth = st.session_state.get("auth")
    if not auth:
        return
    col1, col2, col3 = st.columns([2, 2, 1])
    with col3:
        if st.button("Sair", use_container_width=True):
            st.session_state.pop("auth", None)
            st.session_state.pop("selected_id", None)
            st.rerun()

# =========================
# RENDER
# =========================
def render_chip_list(tags: str):
    if not tags:
        return
    for t in [x.strip() for x in str(tags).split(",") if x.strip()]:
        st.markdown(f'<span class="yvora-chip">{t}</span>', unsafe_allow_html=True)

def render_item_view(item: dict, mode: str):
    st.markdown(f'<div class="yvora-section-title">{item.get("name","")}</div>', unsafe_allow_html=True)
    meta = f'{item.get("category","")} | {item.get("yield","")} | {item.get("total_time_min","")} min'
    st.markdown(f'<div class="yvora-muted">{meta}</div>', unsafe_allow_html=True)

    cover = item.get("cover_photo_url", "")
    if cover:
        st.image(cover, use_container_width=True)

    render_chip_list(item.get("tags", ""))

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

def render_item_edit(item: dict) -> dict:
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

def render_catalog(items_df: pd.DataFrame, module_type: str, search: str, category: str):
    df = items_df.copy()

    df_require_columns(df, ["id", "type", "name"], "aba items")

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
    return df

def render_grid_list(df: pd.DataFrame):
    if df.empty:
        st.info("Nenhum item encontrado.")
        return

    rows = df.to_dict(orient="records")

    cols = st.columns(2)
    for idx, item in enumerate(rows):
        col = cols[idx % 2]
        with col:
            ui_card_open()
            cover = item.get("cover_photo_url", "")
            if cover:
                st.image(cover, use_container_width=True)

            st.markdown(f"**{item.get('name','')}**")
            meta = f"{item.get('category','')} | {item.get('total_time_min','')} min"
            st.markdown(f'<div class="yvora-muted">{meta}</div>', unsafe_allow_html=True)

            if st.button("Abrir", key=f"open_{item.get('id','')}", type="primary", use_container_width=True):
                st.session_state["selected_id"] = item.get("id", "")
                st.rerun()

            ui_card_close()

# =========================
# MAIN
# =========================
def run():
    auth = st.session_state.get("auth")
    ui_header(auth)
    logout_area()

    # Defensive load
    try:
        sh = open_sheet()
        users_df = read_tab_df(sh, USERS_TAB)
        items_df = read_tab_df(sh, ITEMS_TAB)
    except Exception as e:
        show_friendly_error("Falha ao acessar Google Sheets", str(e))
        return

    # Auth gate
    if not st.session_state.get("auth"):
        try:
            if users_df.empty:
                show_friendly_error(
                    "Aba users vazia",
                    "Importe o template e preencha pelo menos 3 usuários (cozinha, chefe, admin).",
                )
                return
            do_login(users_df)
        except Exception as e:
            show_friendly_error("Erro no login", str(e))
        return

    role = st.session_state["auth"]["role"]

    # Tablet controls
    ui_card_open()
    c1, c2, c3, c4 = st.columns([1, 1, 2, 1])
    with c1:
        module = st.radio("Conteúdo", ["Drinks", "Pratos"], horizontal=False)
    with c2:
        mode = st.radio("Modo", ["Serviço", "Treinamento"], horizontal=False)
    with c3:
        search = st.text_input("Buscar por nome ou tag", placeholder="ex: gin, costela, pesto")
        category = st.text_input("Filtrar categoria", placeholder="ex: Entrada, Principal, Clássico")
    with c4:
        if can_edit(role):
            if st.button("Novo", type="primary", use_container_width=True):
                prefix = "D" if module == "Drinks" else "P"
                existing = items_df["id"].astype(str).tolist() if "id" in items_df.columns else []
                new_id = f"{prefix}{str(len(existing)+1).zfill(3)}"
                st.session_state["selected_id"] = new_id
                st.session_state["creating_new"] = True
                st.rerun()
        else:
            st.button("Novo", disabled=True, use_container_width=True)
    ui_card_close()

    module_type = "drink" if module == "Drinks" else "prato"

    try:
        df = render_catalog(items_df, module_type, search, category)
    except Exception as e:
        show_friendly_error("Estrutura da aba items inválida", str(e))
        return

    # Two panes for iPad
    left, right = st.columns([1, 1])

    with left:
        st.markdown('<div class="yvora-section-title">Lista</div>', unsafe_allow_html=True)
        render_grid_list(df)

    with right:
        selected_id = st.session_state.get("selected_id", "")
        creating_new = st.session_state.get("creating_new", False)

        st.markdown('<div class="yvora-section-title">Ficha</div>', unsafe_allow_html=True)

        if not selected_id:
            st.info("Selecione um item na lista.")
            return

        # Create new
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
                "total_time_min": 0,
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

            ui_card_open()
            edited = render_item_edit(base)

            colS, colC = st.columns(2)
            with colS:
                if st.button("Salvar", type="primary", use_container_width=True):
                    try:
                        new_df = upsert_row(items_df, "id", edited)
                        write_tab_df(sh, ITEMS_TAB, new_df)
                        st.session_state["creating_new"] = False
                        st.success("Item criado.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Falha ao salvar: {e}")
            with colC:
                if st.button("Cancelar", use_container_width=True):
                    st.session_state["creating_new"] = False
                    st.session_state["selected_id"] = ""
                    st.rerun()
            ui_card_close()
            return

        # View existing
        match = items_df[items_df["id"].astype(str) == str(selected_id)] if "id" in items_df.columns else pd.DataFrame()
        if match.empty:
            st.warning("Item não encontrado. Se você criou agora, atualize a lista.")
            return

        item = match.iloc[0].to_dict()

        ui_card_open()
        render_item_view(item, mode)
        ui_card_close()

        # Edit only for editor/admin
        if can_edit(role):
            st.write("")
            ui_card_open()
            with st.expander("Editar esta ficha", expanded=False):
                edited = render_item_edit(item)
                if st.button("Salvar alterações", type="primary", use_container_width=True):
                    try:
                        new_df = upsert_row(items_df, "id", edited)
                        write_tab_df(sh, ITEMS_TAB, new_df)
                        st.success("Alterações salvas.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Falha ao salvar: {e}")
            ui_card_close()

try:
    run()
except Exception as e:
    show_friendly_error("Erro inesperado no app", str(e))
