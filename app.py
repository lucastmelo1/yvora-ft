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
html, body, [class*="css"] { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial; }
.stApp { background-color: #EFE7DD; }
.block-container { max-width: 1200px; padding-top: 1rem; }
.card { background: white; border-radius: 18px; padding: 16px; margin-bottom: 16px;
        box-shadow: 0 6px 20px rgba(0,0,0,0.06); }
.title-bar { background: #0E2A47; color: white; padding: 14px 18px; border-radius: 18px;
             margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }
.title-left { display: flex; align-items: center; gap: 12px; }
.title-bar h1 { font-size: 20px; margin: 0; }
.badge { background: rgba(255,255,255,0.15); padding: 8px 14px; border-radius: 999px; font-size: 14px;
         display: flex; gap: 10px; align-items: center; }
.stButton > button { border-radius: 14px; font-size: 16px; padding: 12px; }
.stButton > button[kind="primary"] { background-color: #0E2A47; }
.small-btn > button { padding: 8px 10px !important; font-size: 14px !important; border-radius: 12px !important; }
hr { border: none; border-top: 1px solid rgba(0,0,0,0.08); margin: 10px 0; }
</style>
""", unsafe_allow_html=True)

# ======================================================
# LOGO (na raiz do repo)
# ======================================================
LOGO_CANDIDATES = [
    "Ivora_logo.png", "Ivora_logo.jpg", "Ivora_logo.jpeg", "Ivora_logo.webp",
    "yvora_logo.png", "yvora_logo.jpg", "yvora_logo.jpeg", "yvora_logo.webp"
]

def find_logo_path() -> str | None:
    base = Path(__file__).parent
    for name in LOGO_CANDIDATES:
        p = base / name
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
# AUTH + PERMISSÕES POR MÓDULO (drinks/pratos)
# ======================================================
ROLE_LABEL = {"viewer":"Cozinha","editor":"Chefe","admin":"Administrador"}

# Colunas esperadas em users:
# can_drinks (0/1)
# can_pratos (0/1)
REQUIRED_USER_COLS = ["username", "password", "role", "active", "can_drinks", "can_pratos"]

def logout():
    st.session_state.pop("auth", None)
    st.session_state.pop("item", None)
    st.session_state.pop("login_user", None)
    st.session_state.pop("login_pass", None)
    st.session_state.pop("confirm_delete", None)

def is_admin() -> bool:
    return st.session_state.get("auth", {}).get("role") == "admin"

def can_edit() -> bool:
    return st.session_state.get("auth", {}).get("role") in ["admin", "editor"]

def has_access(module_type: str) -> bool:
    auth = st.session_state.get("auth", {})
    if not auth:
        return False
    if auth.get("role") == "admin":
        return True
    if module_type == "drink":
        return auth.get("can_drinks") == "1"
    return auth.get("can_pratos") == "1"

def validate_users_df(users: pd.DataFrame):
    missing = [c for c in REQUIRED_USER_COLS if c not in users.columns]
    if missing:
        raise ValueError(f"Faltam colunas na aba users: {', '.join(missing)}")

def login(users):
    validate_users_df(users)

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Login")

    u = st.text_input("Usuário", key="login_user")
    p = st.text_input("Senha", type="password", key="login_pass")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Entrar", type="primary", use_container_width=True):
            df = users.copy()
            df["active"] = df["active"].astype(str)
            df["can_drinks"] = df["can_drinks"].astype(str)
            df["can_pratos"] = df["can_pratos"].astype(str)

            match = df[
                (df["username"].astype(str) == str(u)) &
                (df["password"].astype(str) == str(p)) &
                (df["active"] == "1")
            ]
            if match.empty:
                st.error("Usuário ou senha inválidos (ou usuário inativo).")
            else:
                row = match.iloc[0]
                st.session_state["auth"] = {
                    "username": str(row["username"]),
                    "role": str(row["role"]),
                    "can_drinks": str(row["can_drinks"]),
                    "can_pratos": str(row["can_pratos"]),
                }
                st.session_state.pop("item", None)
                st.rerun()
    with col2:
        if st.button("Limpar", use_container_width=True):
            st.session_state["login_user"] = ""
            st.session_state["login_pass"] = ""

    st.markdown("</div>", unsafe_allow_html=True)

# ======================================================
# HEADER (logo + trocar usuário)
# ======================================================
def header():
    auth = st.session_state.get("auth")
    user_text = "Acesso"
    if auth:
        role = auth.get("role", "")
        user_text = f"{ROLE_LABEL.get(role, role)} | {auth.get('username','')}"

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
        col1, col2, col3 = st.columns([2, 2, 2])
        with col3:
            st.markdown('<div class="small-btn">', unsafe_allow_html=True)
            if st.button("Trocar usuário", use_container_width=True):
                logout()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

# ======================================================
# ITENS: CRUD ADMIN
# ======================================================
ITEM_COLUMNS = [
    "id", "type", "name", "category", "tags", "yield", "total_time_min",
    "cover_photo_url", "training_video_url",
    "service_ingredients", "service_steps", "service_plating",
    "training_mise_en_place", "training_details", "training_common_mistakes"
]

def ensure_item_schema(items: pd.DataFrame) -> pd.DataFrame:
    out = items.copy()
    for c in ITEM_COLUMNS:
        if c not in out.columns:
            out[c] = ""
    return out

def next_id(items: pd.DataFrame, prefix: str) -> str:
    # prefix: "D" ou "P"
    if items.empty or "id" not in items.columns:
        return f"{prefix}001"
    ids = items["id"].astype(str).tolist()
    nums = []
    for x in ids:
        if x.startswith(prefix):
            tail = x.replace(prefix, "")
            if tail.isdigit():
                nums.append(int(tail))
    n = max(nums) + 1 if nums else 1
    return f"{prefix}{str(n).zfill(3)}"

def upsert_item(items: pd.DataFrame, item: dict) -> pd.DataFrame:
    out = items.copy()
    out = ensure_item_schema(out)
    item_id = str(item.get("id", "")).strip()
    if not item_id:
        raise ValueError("ID do item não pode ser vazio.")
    mask = out["id"].astype(str) == item_id
    if mask.any():
        idx = out.index[mask][0]
        for k, v in item.items():
            if k in out.columns:
                out.at[idx, k] = str(v)
    else:
        # adiciona novo
        row = {c: "" for c in out.columns}
        for k, v in item.items():
            if k in out.columns:
                row[k] = str(v)
        out = pd.concat([out, pd.DataFrame([row])], ignore_index=True)
    return out

def delete_item(items: pd.DataFrame, item_id: str) -> pd.DataFrame:
    out = items.copy()
    if out.empty:
        return out
    out = out[out["id"].astype(str) != str(item_id)].copy()
    return out

# ======================================================
# APP PRINCIPAL
# ======================================================
def main():
    header()

    users_tab = st.secrets.get("USERS_TAB", "users")
    items_tab = st.secrets.get("ITEMS_TAB", "items")

    try:
        users = read_sheet(users_tab)
    except Exception as e:
        st.error(f"Erro lendo aba users: {e}")
        return

    if "auth" not in st.session_state:
        try:
            login(users)
        except Exception as e:
            st.error(str(e))
        return

    try:
        items = read_sheet(items_tab)
        items = ensure_item_schema(items)
    except Exception as e:
        st.error(f"Erro lendo aba items: {e}")
        return

    auth = st.session_state["auth"]

    # ==================================================
    # FILTRA MÓDULOS PELO USUÁRIO
    # ==================================================
    allowed_modules = []
    if auth.get("role") == "admin":
        allowed_modules = ["Drinks", "Pratos"]
    else:
        if auth.get("can_drinks") == "1":
            allowed_modules.append("Drinks")
        if auth.get("can_pratos") == "1":
            allowed_modules.append("Pratos")

    if not allowed_modules:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.error("Este usuário não tem acesso a Drinks nem a Pratos. Ajuste can_drinks/can_pratos na aba users.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ==================================================
    # Seletores + botão NOVO (ADMIN)
    # ==================================================
    colA, colB, colC, colD = st.columns([1, 1, 2, 1])
    with colA:
        tipo = st.radio("Conteúdo", allowed_modules)
    with colB:
        modo = st.radio("Modo", ["Serviço", "Treinamento"])
    with colC:
        busca = st.text_input("Buscar", placeholder="nome / tag")
    with colD:
        if is_admin():
            if st.button("Novo", type="primary", use_container_width=True):
                prefix = "D" if tipo == "Drinks" else "P"
                new_id = next_id(items, prefix)
                st.session_state["item"] = new_id
                st.session_state["creating_new"] = True
                st.rerun()

    tipo_val = "drink" if tipo == "Drinks" else "prato"

    if not has_access(tipo_val):
        st.error("Sem permissão para acessar este módulo.")
        return

    # Filtra itens do módulo
    df = items[items["type"].astype(str).str.lower() == tipo_val].copy()

    if busca and not df.empty:
        b = busca.strip().lower()
        tags = df["tags"].astype(str) if "tags" in df.columns else ""
        df = df[df["name"].astype(str).str.lower().str.contains(b) | tags.str.lower().str.contains(b)]

    # ==================================================
    # Lista
    # ==================================================
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Itens")

    if df.empty:
        st.info("Nenhum item encontrado.")
    else:
        for _, row in df.sort_values("name").iterrows():
            if st.button(str(row["name"]), use_container_width=True, key=f"btn_{row['id']}"):
                st.session_state["item"] = str(row["id"])
                st.session_state.pop("creating_new", None)
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if "item" not in st.session_state:
        return

    item_id = str(st.session_state["item"])
    creating_new = st.session_state.get("creating_new", False)

    # Se é novo, cria dict base; se não, pega do DF
    if creating_new:
        if not is_admin():
            st.error("Somente administrador pode criar itens.")
            return

        base = {
            "id": item_id,
            "type": tipo_val,
            "name": "",
            "category": "",
            "tags": "",
            "yield": "",
            "total_time_min": "0",
            "cover_photo_url": "",
            "training_video_url": "",
            "service_ingredients": "",
            "service_steps": "",
            "service_plating": "",
            "training_mise_en_place": "",
            "training_details": "",
            "training_common_mistakes": "",
        }
        item = base
    else:
        match = items[items["id"].astype(str) == item_id]
        if match.empty:
            st.warning("Item não encontrado na base.")
            return
        item = match.iloc[0].to_dict()

        # Proteção: impede abrir item de outro tipo
        if str(item.get("type", "")).lower().strip() != tipo_val:
            st.session_state.pop("item", None)
            st.warning("O item selecionado não pertence ao módulo atual.")
            st.rerun()

    # ==================================================
    # Visualização
    # ==================================================
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader(str(item.get("name", "")) if not creating_new else "Novo item")

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

    # ==================================================
    # ADMIN: CRIAR / EDITAR TUDO / EXCLUIR
    # ==================================================
    if is_admin():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Administrador · Gerenciar item")

        edited = dict(item)

        col1, col2 = st.columns([1, 1])
        with col1:
            edited["type"] = st.selectbox("Tipo", ["drink", "prato"], index=0 if tipo_val == "drink" else 1)
            edited["category"] = st.text_input("Categoria", value=str(item.get("category", "")))
            edited["yield"] = st.text_input("Rendimento", value=str(item.get("yield", "")))
        with col2:
            edited["id"] = st.text_input("ID", value=str(item.get("id", "")), disabled=True)
            edited["name"] = st.text_input("Título (nome)", value=str(item.get("name", "")))
            edited["total_time_min"] = st.text_input("Tempo total (min)", value=str(item.get("total_time_min", "0")))

        edited["tags"] = st.text_input("Tags (separadas por vírgula)", value=str(item.get("tags", "")))
        edited["cover_photo_url"] = st.text_input("Foto capa (URL)", value=str(item.get("cover_photo_url", "")))
        edited["training_video_url"] = st.text_input("Vídeo treinamento (URL)", value=str(item.get("training_video_url", "")))

        st.markdown("<hr/>", unsafe_allow_html=True)

        st.markdown("### Modo Serviço")
        edited["service_ingredients"] = st.text_area("Ingredientes", value=str(item.get("service_ingredients", "")), height=140)
        edited["service_steps"] = st.text_area("Passos", value=str(item.get("service_steps", "")), height=140)
        edited["service_plating"] = st.text_area("Montagem", value=str(item.get("service_plating", "")), height=120)

        st.markdown("<hr/>", unsafe_allow_html=True)

        st.markdown("### Modo Treinamento")
        edited["training_mise_en_place"] = st.text_area("Mise en place", value=str(item.get("training_mise_en_place", "")), height=120)
        edited["training_details"] = st.text_area("Detalhes", value=str(item.get("training_details", "")), height=120)
        edited["training_common_mistakes"] = st.text_area("Erros comuns", value=str(item.get("training_common_mistakes", "")), height=120)

        colS, colX = st.columns([2, 1])

        with colS:
            if st.button("Salvar (Admin)", type="primary", use_container_width=True):
                try:
                    items2 = upsert_item(items, edited)
                    write_sheet(items_tab, items2)
                    st.session_state["creating_new"] = False
                    st.success("Salvo com sucesso.")
                    time.sleep(0.4)
                    st.rerun()
                except Exception as e:
                    st.error(f"Falha ao salvar: {e}")

        with colX:
            if not creating_new:
                if st.button("Excluir", use_container_width=True):
                    st.session_state["confirm_delete"] = True

        # Confirmação de delete
        if st.session_state.get("confirm_delete") and not creating_new:
            st.warning("Confirme a exclusão definitiva deste item.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Confirmar exclusão", type="primary", use_container_width=True):
                    try:
                        items2 = delete_item(items, item_id)
                        write_sheet(items_tab, items2)
                        st.session_state.pop("confirm_delete", None)
                        st.session_state.pop("item", None)
                        st.success("Item excluído.")
                        time.sleep(0.4)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Falha ao excluir: {e}")
            with c2:
                if st.button("Cancelar", use_container_width=True):
                    st.session_state.pop("confirm_delete", None)
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # ==================================================
    # CHEFE (editor): editar campos de preparo, não ID/nome/tipo
    # ==================================================
    elif can_edit():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Chefe · Editar conteúdo")

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
            try:
                items2 = upsert_item(items, edited)
                write_sheet(items_tab, items2)
                st.success("Alterações salvas.")
                time.sleep(0.4)
                st.rerun()
            except Exception as e:
                st.error(f"Falha ao salvar: {e}")

        st.markdown("</div>", unsafe_allow_html=True)

# ======================================================
# START
# ======================================================
main()
