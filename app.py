import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Fichas Técnicas", layout="wide")

# =========================
# Config
# =========================
SHEET_ID = st.secrets.get("SHEET_ID", "")
USERS_TAB = st.secrets.get("USERS_TAB", "users")
ITEMS_TAB = st.secrets.get("ITEMS_TAB", "items")

ROLE_LABEL = {
    "viewer": "Cozinha",
    "editor": "Chefe",
    "admin": "Administrador",
}

def is_editor(role: str) -> bool:
    return role in ["editor", "admin"]

# =========================
# Google Sheets
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

def read_tab_as_df(sh, tab_name: str) -> pd.DataFrame:
    ws = sh.worksheet(tab_name)
    data = ws.get_all_records()
    return pd.DataFrame(data)

def write_df_to_tab(sh, tab_name: str, df: pd.DataFrame):
    ws = sh.worksheet(tab_name)
    ws.clear()
    ws.update([df.columns.tolist()] + df.fillna("").astype(str).values.tolist())

# =========================
# Parsing helpers
# =========================
def parse_lines(cell: str) -> list[str]:
    if cell is None:
        return []
    s = str(cell).strip()
    if not s:
        return []
    return [x.strip() for x in s.split("\n") if x.strip()]

def parse_csv_urls(cell: str) -> list[str]:
    if cell is None:
        return []
    s = str(cell).strip()
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]

def parse_ingredients(cell: str) -> list[dict]:
    """
    Each line: item|qty|unit
    """
    rows = []
    for line in parse_lines(cell):
        parts = [p.strip() for p in line.split("|")]
        item = parts[0] if len(parts) > 0 else ""
        qty = parts[1] if len(parts) > 1 else ""
        unit = parts[2] if len(parts) > 2 else ""
        rows.append({"item": item, "qty": qty, "unit": unit})
    return rows

def ingredients_to_text(rows: list[dict]) -> str:
    out = []
    for r in rows:
        out.append(f"{r.get('item','')}|{r.get('qty','')}|{r.get('unit','')}")
    return "\n".join(out).strip()

# =========================
# Auth
# =========================
def login(users_df: pd.DataFrame):
    st.title("Fichas Técnicas")
    st.caption("Login")

    u = st.text_input("Usuário", key="login_user")
    p = st.text_input("Senha", type="password", key="login_pass")

    if st.button("Entrar", type="primary"):
        if users_df.empty:
            st.error("A aba users está vazia.")
            return

        df = users_df.copy()
        for c in ["username", "password", "role", "active"]:
            if c not in df.columns:
                st.error(f"Coluna faltando na aba users: {c}")
                return

        df["active"] = df["active"].astype(str)
        ok = df[
            (df["username"].astype(str) == str(u).strip())
            & (df["password"].astype(str) == str(p).strip())
            & (df["active"] == "1")
        ]

        if ok.empty:
            st.error("Usuário ou senha inválidos, ou usuário inativo.")
            return

        row = ok.iloc[0].to_dict()
        st.session_state["auth"] = {
            "username": row["username"],
            "role": row["role"],
        }
        st.success("Login realizado.")
        st.rerun()

def logout_box():
    auth = st.session_state.get("auth")
    if not auth:
        return
    with st.sidebar:
        st.markdown("### Sessão")
        st.write(f"Usuário: **{auth['username']}**")
        st.write(f"Perfil: **{ROLE_LABEL.get(auth['role'], auth['role'])}**")
        if st.button("Sair"):
            st.session_state.pop("auth", None)
            st.rerun()

# =========================
# UI
# =========================
def item_card(title: str, cover_url: str, subtitle: str = ""):
    with st.container(border=True):
        cols = st.columns([1, 2])
        with cols[0]:
            if cover_url:
                st.image(cover_url, use_container_width=True)
            else:
                st.info("Sem foto")
        with cols[1]:
            st.subheader(title)
            if subtitle:
                st.caption(subtitle)

def render_item_view(item: dict, mode: str):
    st.subheader(item.get("name", ""))
    meta_cols = st.columns(4)
    meta_cols[0].write(f"Tipo: **{item.get('type','')}**")
    meta_cols[1].write(f"Categoria: **{item.get('category','')}**")
    meta_cols[2].write(f"Rendimento: **{item.get('yield','')}**")
    meta_cols[3].write(f"Tempo: **{item.get('total_time_min','')} min**")

    cover = item.get("cover_photo_url", "")
    if cover:
        st.image(cover, use_container_width=True)

    tags = item.get("tags", "")
    if tags:
        st.caption(f"Tags: {tags}")

    if mode == "Serviço":
        st.markdown("### Ingredientes")
        ing = parse_ingredients(item.get("service_ingredients", ""))
        if ing:
            st.dataframe(pd.DataFrame(ing), use_container_width=True, hide_index=True)
        else:
            st.info("Sem ingredientes cadastrados.")

        st.markdown("### Passo a passo")
        steps = parse_lines(item.get("service_steps", ""))
        if steps:
            for i, s in enumerate(steps, 1):
                st.write(f"{i}. {s}")
        else:
            st.info("Sem passos cadastrados.")

        st.markdown("### Montagem e padrão")
        plating = parse_lines(item.get("service_plating", ""))
        if plating:
            for p in plating:
                st.write(f"- {p}")
        else:
            st.info("Sem montagem cadastrada.")

    else:
        st.markdown("### Mise en place")
        mise = parse_lines(item.get("training_mise_en_place", ""))
        if mise:
            for m in mise:
                st.write(f"- {m}")
        else:
            st.info("Sem mise en place cadastrado.")

        st.markdown("### Detalhes")
        det = parse_lines(item.get("training_details", ""))
        if det:
            for d in det:
                st.write(f"- {d}")
        else:
            st.info("Sem detalhes cadastrados.")

        st.markdown("### Erros comuns")
        err = parse_lines(item.get("training_common_mistakes", ""))
        if err:
            for e in err:
                st.write(f"- {e}")
        else:
            st.info("Sem erros comuns cadastrados.")

        st.markdown("### Checklist de qualidade")
        qc = parse_lines(item.get("training_quality_check", ""))
        if qc:
            for q in qc:
                st.write(f"- {q}")
        else:
            st.info("Sem checklist cadastrado.")

        video = item.get("training_video_url", "")
        if video:
            st.markdown("### Vídeo")
            st.link_button("Abrir vídeo", video)

        steps_photos = parse_csv_urls(item.get("step_photos_urls", ""))
        if steps_photos:
            st.markdown("### Fotos de etapas")
            for url in steps_photos:
                st.image(url, use_container_width=True)

def render_item_edit(item: dict) -> dict:
    st.markdown("### Editar ficha")
    edited = dict(item)

    c1, c2, c3 = st.columns(3)
    edited["name"] = c1.text_input("Nome", value=item.get("name", ""))
    edited["category"] = c2.text_input("Categoria", value=item.get("category", ""))
    edited["tags"] = c3.text_input("Tags (vírgula)", value=item.get("tags", ""))

    c4, c5, c6 = st.columns(3)
    edited["yield"] = c4.text_input("Rendimento", value=item.get("yield", ""))
    edited["total_time_min"] = c5.number_input("Tempo total (min)", min_value=0, value=int(item.get("total_time_min") or 0))
    edited["cover_photo_url"] = c6.text_input("Foto capa (Drive URL)", value=item.get("cover_photo_url", ""))

    edited["training_video_url"] = st.text_input("Vídeo treinamento (Drive URL)", value=item.get("training_video_url", ""))
    edited["step_photos_urls"] = st.text_area("Fotos de etapas (URLs separadas por vírgula)", value=item.get("step_photos_urls", ""))

    st.markdown("#### Modo Serviço")
    edited["service_ingredients"] = st.text_area("Ingredientes (1 por linha: item|qty|unit)", value=item.get("service_ingredients", ""), height=160)
    edited["service_steps"] = st.text_area("Passos (1 por linha)", value=item.get("service_steps", ""), height=160)
    edited["service_plating"] = st.text_area("Montagem (1 por linha)", value=item.get("service_plating", ""), height=120)

    st.markdown("#### Modo Treinamento")
    edited["training_mise_en_place"] = st.text_area("Mise en place (1 por linha)", value=item.get("training_mise_en_place", ""), height=120)
    edited["training_details"] = st.text_area("Detalhes (1 por linha)", value=item.get("training_details", ""), height=120)
    edited["training_common_mistakes"] = st.text_area("Erros comuns (1 por linha)", value=item.get("training_common_mistakes", ""), height=120)
    edited["training_quality_check"] = st.text_area("Checklist qualidade (1 por linha)", value=item.get("training_quality_check", ""), height=120)

    return edited

def upsert_item_df(items_df: pd.DataFrame, updated: dict) -> pd.DataFrame:
    df = items_df.copy()
    if "id" not in df.columns:
        df["id"] = ""
    if updated["id"] in df["id"].astype(str).tolist():
        idx = df.index[df["id"].astype(str) == str(updated["id"])][0]
        for k, v in updated.items():
            if k not in df.columns:
                df[k] = ""
            df.at[idx, k] = v
    else:
        for k in updated.keys():
            if k not in df.columns:
                df[k] = ""
        df = pd.concat([df, pd.DataFrame([updated])], ignore_index=True)
    return df

def main_app(users_df: pd.DataFrame, items_df: pd.DataFrame, sh):
    auth = st.session_state.get("auth")
    role = auth["role"]

    logout_box()

    with st.sidebar:
        st.markdown("### Navegação")
        module = st.radio("Escolha", ["Drinks", "Pratos"], index=0)
        mode = st.radio("Modo", ["Serviço", "Treinamento"], index=0)

        st.markdown("### Busca")
        q = st.text_input("Buscar por nome ou tag")

        st.markdown("### Filtro")
        category_filter = st.text_input("Categoria (opcional)")

        st.markdown("### Ações")
        can_edit = is_editor(role)
        add_new = st.button("Novo item", disabled=not can_edit)

    if items_df.empty:
        st.warning("A aba items está vazia.")
        return

    df = items_df.copy()

    required_cols = ["id", "type", "name"]
    for c in required_cols:
        if c not in df.columns:
            st.error(f"Coluna faltando na aba items: {c}")
            return

    type_value = "drink" if module == "Drinks" else "prato"
    df = df[df["type"].astype(str).str.lower() == type_value]

    if q:
        qn = q.strip().lower()
        df = df[
            df["name"].astype(str).str.lower().str.contains(qn)
            | df.get("tags", pd.Series([""] * len(df))).astype(str).str.lower().str.contains(qn)
        ]

    if category_filter:
        cf = category_filter.strip().lower()
        df = df[df.get("category", pd.Series([""] * len(df))).astype(str).str.lower().str.contains(cf)]

    df = df.sort_values("name")

    if add_new:
        new_id = f"{'D' if type_value=='drink' else 'P'}{str(len(items_df) + 1).zfill(3)}"
        st.session_state["selected_item_id"] = new_id
        st.session_state["creating_new"] = True
        st.rerun()

    left, right = st.columns([1, 2])

    with left:
        st.markdown("## Lista")
        if df.empty:
            st.info("Nenhum item encontrado com os filtros atuais.")
        else:
            for _, row in df.iterrows():
                item = row.to_dict()
                subtitle = f"{item.get('category','')}"
                if st.button(item.get("name", "Sem nome"), use_container_width=True):
                    st.session_state["selected_item_id"] = item["id"]
                    st.session_state["creating_new"] = False
                    st.rerun()
                st.caption(subtitle)

    with right:
        selected_id = st.session_state.get("selected_item_id")
        creating_new = st.session_state.get("creating_new", False)

        if not selected_id:
            st.info("Selecione um item na lista.")
            return

        if creating_new:
            base = {
                "id": selected_id,
                "type": type_value,
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
            st.markdown("## Novo item")
            if not is_editor(role):
                st.error("Sem permissão para criar.")
                return

            edited = render_item_edit(base)
            csave, ccancel = st.columns(2)
            if csave.button("Salvar novo item", type="primary"):
                new_df = upsert_item_df(items_df, edited)
                write_df_to_tab(sh, ITEMS_TAB, new_df)
                st.success("Item criado.")
                st.session_state["creating_new"] = False
                st.rerun()
            if ccancel.button("Cancelar"):
                st.session_state["creating_new"] = False
                st.session_state["selected_item_id"] = None
                st.rerun()

        else:
            match = items_df[items_df["id"].astype(str) == str(selected_id)]
            if match.empty:
                st.error("Item não encontrado.")
                return

            item = match.iloc[0].to_dict()

            st.markdown("## Ficha")
            item_card(item.get("name", ""), item.get("cover_photo_url", ""), item.get("category", ""))

            tab_view, tab_edit = st.tabs(["Ver", "Editar"])
            with tab_view:
                render_item_view(item, mode)

            with tab_edit:
                if not is_editor(role):
                    st.info("Somente Chefe ou Admin podem editar.")
                else:
                    edited = render_item_edit(item)
                    if st.button("Salvar alterações", type="primary"):
                        new_df = upsert_item_df(items_df, edited)
                        write_df_to_tab(sh, ITEMS_TAB, new_df)
                        st.success("Alterações salvas.")
                        st.rerun()

# =========================
# App entry
# =========================
def run():
    if not SHEET_ID:
        st.error("Faltou configurar SHEET_ID em secrets.")
        return

    client = get_gspread_client()
    sh = client.open_by_key(SHEET_ID)

    users_df = read_tab_as_df(sh, USERS_TAB)
    items_df = read_tab_as_df(sh, ITEMS_TAB)

    auth = st.session_state.get("auth")
    if not auth:
        login(users_df)
        return

    main_app(users_df, items_df, sh)

run()
