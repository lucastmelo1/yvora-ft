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
.card {
  background: white; border-radius: 18px; padding: 16px; margin-bottom: 16px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.06);
}
.title-bar {
  background: #0E2A47; color: white; padding: 14px 18px; border-radius: 18px;
  margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center;
}
.title-left { display: flex; align-items: center; gap: 12px; }
.title-bar h1 { font-size: 20px; margin: 0; }
.badge {
  background: rgba(255,255,255,0.15); padding: 8px 14px; border-radius: 999px; font-size: 14px;
  display: flex; gap: 10px; align-items: center;
}
.stButton > button { border-radius: 14px; font-size: 16px; padding: 12px; }
.stButton > button[kind="primary"] { background-color: #0E2A47; }
.small-btn > button { padding: 8px 10px !important; font-size: 14px !important; border-radius: 12px !important; }
hr { border: none; border-top: 1px solid rgba(0,0,0,0.08); margin: 10px 0; }
.muted { color: rgba(0,0,0,0.55); font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# ======================================================
# LOGO (na raiz do repo)
# ======================================================
LOGO_CANDIDATES = [
    "Ivora_logo.png", "Ivora_logo.jpg", "Ivora_logo.jpeg", "Ivora_logo.webp",
    "yvora_logo.png", "yvora_logo.jpg", "yvora_logo.jpeg", "yvora_logo.webp",
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

def read_sheet(tab: str) -> pd.DataFrame:
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=st.secrets["SHEET_ID"],
        range=tab
    ).execute()

    values = result.get("values", [])
    if not values:
        return pd.DataFrame()

    # garante colunas únicas
    cols = values[0]
    df = pd.DataFrame(values[1:], columns=cols)
    return df

def write_sheet(tab: str, df: pd.DataFrame):
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
ROLE_LABEL = {"viewer": "Cozinha", "editor": "Chefe", "admin": "Administrador"}
REQUIRED_USER_COLS = ["username", "password", "role", "active", "can_drinks", "can_pratos"]

def logout():
    st.session_state.pop("auth", None)
    st.session_state.pop("item", None)
    st.session_state.pop("login_user", None)
    st.session_state.pop("login_pass", None)
    st.session_state.pop("confirm_delete", None)
    st.session_state.pop("creating_new", None)

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

def login(users: pd.DataFrame):
    validate_users_df(users)

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Login")

    u = st.text_input("Usuário", key="login_user")
    p = st.text_input("Senha", type="password", key="login_pass")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Entrar", type="primary", use_container_width=True):
            df = users.copy()
            for c in ["active", "can_drinks", "can_pratos"]:
                df[c] = df[c].astype(str)

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
                st.session_state.pop("creating_new", None)
                st.rerun()
    with col2:
        if st.button("Limpar", use_container_width=True):
            st.session_state["login_user"] = ""
            st.session_state["login_pass"] = ""

    st.markdown("</div>", unsafe_allow_html=True)

# ======================================================
# HEADER
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
# ITENS: helpers dinâmicos de campos
# ======================================================
BASE_ITEM_COLS = ["id", "type", "name"]  # mínimos para o app funcionar

PREFERRED_GENERAL_ORDER = [
    "name", "category", "tags", "yield", "total_time_min",
    "cover_photo_url", "training_video_url"
]

def ensure_item_min_schema(items: pd.DataFrame) -> pd.DataFrame:
    out = items.copy()
    for c in BASE_ITEM_COLS:
        if c not in out.columns:
            out[c] = ""
    return out

def next_id(items: pd.DataFrame, prefix: str) -> str:
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
    out = ensure_item_min_schema(out)
    item_id = str(item.get("id", "")).strip()
    if not item_id:
        raise ValueError("ID do item não pode ser vazio.")

    # garante que todas as chaves existam como colunas
    for k in item.keys():
        if k not in out.columns:
            out[k] = ""

    mask = out["id"].astype(str) == item_id
    if mask.any():
        idx = out.index[mask][0]
        for k, v in item.items():
            out.at[idx, k] = str(v)
    else:
        row = {c: "" for c in out.columns}
        for k, v in item.items():
            row[k] = str(v)
        out = pd.concat([out, pd.DataFrame([row])], ignore_index=True)

    return out

def delete_item(items: pd.DataFrame, item_id: str) -> pd.DataFrame:
    if items.empty:
        return items
    return items[items["id"].astype(str) != str(item_id)].copy()

def prettify_label(col: str) -> str:
    # transforma snake_case em rótulo amigável
    s = col.replace("_", " ").strip()
    return s[:1].upper() + s[1:]

def render_text_sections(item: dict, cols: list[str]):
    # mostra apenas campos com conteúdo
    any_shown = False
    for c in cols:
        val = str(item.get(c, "")).strip()
        if val:
            any_shown = True
            st.markdown(f"### {prettify_label(c)}")
            st.text(val)
    if not any_shown:
        st.info("Sem informações preenchidas neste modo.")

def get_mode_cols(all_cols: list[str], prefix: str) -> list[str]:
    # retorna colunas por prefixo, mas respeita ordenação básica quando existir
    pref = [c for c in all_cols if c.startswith(prefix)]
    # ordena: ingredients, steps, plating primeiro quando existirem
    priority = [
        f"{prefix}ingredients",
        f"{prefix}steps",
        f"{prefix}plating",
        f"{prefix}mise_en_place",
        f"{prefix}details",
        f"{prefix}common_mistakes",
    ]
    ordered = []
    for p in priority:
        if p in pref:
            ordered.append(p)
    for c in sorted(pref):
        if c not in ordered:
            ordered.append(c)
    return ordered

def get_general_cols(all_cols: list[str]) -> list[str]:
    gens = []
    for c in PREFERRED_GENERAL_ORDER:
        if c in all_cols:
            gens.append(c)
    # qualquer coluna que não seja base e não seja service_/training_ vai para "extras"
    extras = [
        c for c in all_cols
        if c not in gens
        and c not in BASE_ITEM_COLS
        and not c.startswith("service_")
        and not c.startswith("training_")
    ]
    # mantemos ordem estável
    return gens, sorted(extras)

# ======================================================
# APP
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
        items = ensure_item_min_schema(items)
    except Exception as e:
        st.error(f"Erro lendo aba items: {e}")
        return

    auth = st.session_state["auth"]

    # módulos permitidos
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

    # seletores
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

    # filtra itens
    df = items[items["type"].astype(str).str.lower() == tipo_val].copy()

    if busca and not df.empty:
        b = busca.strip().lower()
        name_ok = df["name"].astype(str).str.lower().str.contains(b) if "name" in df.columns else False
        tags_ok = df["tags"].astype(str).str.lower().str.contains(b) if "tags" in df.columns else False
        df = df[name_ok | tags_ok]

    # lista
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Itens")
    if df.empty:
        st.info("Nenhum item encontrado.")
    else:
        show = df.sort_values("name" if "name" in df.columns else "id")
        for _, row in show.iterrows():
            label = str(row.get("name", row.get("id", ""))).strip() or str(row.get("id", ""))
            if st.button(label, use_container_width=True, key=f"btn_{row.get('id','')}"):
                st.session_state["item"] = str(row.get("id", ""))
                st.session_state.pop("creating_new", None)
                st.session_state.pop("confirm_delete", None)
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if "item" not in st.session_state:
        return

    item_id = str(st.session_state["item"])
    creating_new = bool(st.session_state.get("creating_new", False))

    all_cols = list(items.columns)

    if creating_new:
        if not is_admin():
            st.error("Somente administrador pode criar itens.")
            return
        # cria um item base, mas já com todas as colunas existentes na planilha
        item = {c: "" for c in all_cols}
        item["id"] = item_id
        item["type"] = tipo_val
        item["name"] = ""
    else:
        match = items[items["id"].astype(str) == item_id]
        if match.empty:
            st.warning("Item não encontrado na base.")
            return
        item = match.iloc[0].to_dict()

        if str(item.get("type", "")).lower().strip() != tipo_val:
            st.session_state.pop("item", None)
            st.warning("O item selecionado não pertence ao módulo atual.")
            st.rerun()

    # ==================================================
    # VISUALIZAÇÃO
    # ==================================================
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("Novo item" if creating_new else str(item.get("name", "")))

    cover = str(item.get("cover_photo_url", "")).strip()
    if cover:
        st.image(cover, use_container_width=True)

    # gerais
    general_cols, extra_general = get_general_cols(all_cols)
    meta_parts = []
    for c in ["category", "yield", "total_time_min"]:
        if c in all_cols:
            v = str(item.get(c, "")).strip()
            if v:
                meta_parts.append(f"{prettify_label(c)}: {v}")
    if meta_parts:
        st.markdown(f"<div class='muted'>{' | '.join(meta_parts)}</div>", unsafe_allow_html=True)

    # conteúdo por modo
    if modo == "Serviço":
        mode_cols = get_mode_cols(all_cols, "service_")
        render_text_sections(item, mode_cols)
    else:
        mode_cols = get_mode_cols(all_cols, "training_")
        render_text_sections(item, mode_cols)

        # vídeo no treinamento, se existir
        if "training_video_url" in all_cols:
            vid = str(item.get("training_video_url", "")).strip()
            if vid:
                st.link_button("Assistir vídeo", vid, use_container_width=True)

    # mostra campos gerais extras preenchidos (somente leitura)
    filled_extras = []
    for c in extra_general:
        v = str(item.get(c, "")).strip()
        if v:
            filled_extras.append(c)
    if filled_extras:
        st.markdown("<hr/>", unsafe_allow_html=True)
        st.markdown("### Informações adicionais")
        for c in filled_extras:
            st.markdown(f"**{prettify_label(c)}**")
            st.text(str(item.get(c, "")).strip())

    st.markdown("</div>", unsafe_allow_html=True)

    # ==================================================
    # ADMIN CRUD COMPLETO
    # ==================================================
    if is_admin():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Administrador · Gerenciar item")

        edited = dict(item)

        # campos base e gerais
        col1, col2 = st.columns([1, 1])
        with col1:
            edited["type"] = st.selectbox("Tipo", ["drink", "prato"], index=0 if tipo_val == "drink" else 1)
            if "category" in all_cols:
                edited["category"] = st.text_input("Categoria", value=str(item.get("category", "")))
            if "yield" in all_cols:
                edited["yield"] = st.text_input("Rendimento", value=str(item.get("yield", "")))
        with col2:
            edited["id"] = st.text_input("ID", value=str(item.get("id", "")), disabled=True)
            edited["name"] = st.text_input("Título (nome)", value=str(item.get("name", "")))
            if "total_time_min" in all_cols:
                edited["total_time_min"] = st.text_input("Tempo total (min)", value=str(item.get("total_time_min", "")))

        if "tags" in all_cols:
            edited["tags"] = st.text_input("Tags (separadas por vírgula)", value=str(item.get("tags", "")))
        if "cover_photo_url" in all_cols:
            edited["cover_photo_url"] = st.text_input("Foto capa (URL)", value=str(item.get("cover_photo_url", "")))
        if "training_video_url" in all_cols:
            edited["training_video_url"] = st.text_input("Vídeo treinamento (URL)", value=str(item.get("training_video_url", "")))

        st.markdown("<hr/>", unsafe_allow_html=True)

        # edita TODOS os campos service_
        service_cols = get_mode_cols(all_cols, "service_")
        with st.expander("Campos de Serviço (service_*)", expanded=True):
            if not service_cols:
                st.info("Nenhuma coluna service_* encontrada na planilha.")
            for c in service_cols:
                edited[c] = st.text_area(prettify_label(c), value=str(item.get(c, "")), height=120)

        # edita TODOS os campos training_
        training_cols = get_mode_cols(all_cols, "training_")
        with st.expander("Campos de Treinamento (training_*)", expanded=True):
            if not training_cols:
                st.info("Nenhuma coluna training_* encontrada na planilha.")
            for c in training_cols:
                edited[c] = st.text_area(prettify_label(c), value=str(item.get(c, "")), height=120)

        # edita quaisquer outros campos não cobertos
        covered = set(BASE_ITEM_COLS) | set(general_cols) | set(extra_general) | set(service_cols) | set(training_cols)
        other_cols = [c for c in all_cols if c not in covered]
        if other_cols:
            with st.expander("Outros campos (extras)", expanded=False):
                for c in sorted(other_cols):
                    if c in BASE_ITEM_COLS:
                        continue
                    edited[c] = st.text_input(prettify_label(c), value=str(item.get(c, "")))

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
    # CHEFE: editar campos de conteúdo, mas sem mexer em name/type/id
    # ==================================================
    elif can_edit():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.subheader("Chefe · Editar conteúdo")

        edited = dict(item)

        # chef pode editar conteúdo e links, mantendo título/tipo
        if "cover_photo_url" in all_cols:
            edited["cover_photo_url"] = st.text_input("Foto capa (URL)", value=str(item.get("cover_photo_url", "")))
        if "training_video_url" in all_cols:
            edited["training_video_url"] = st.text_input("Vídeo treinamento (URL)", value=str(item.get("training_video_url", "")))

        service_cols = get_mode_cols(all_cols, "service_")
        training_cols = get_mode_cols(all_cols, "training_")

        with st.expander("Editar Serviço (service_*)", expanded=True):
            for c in service_cols:
                edited[c] = st.text_area(prettify_label(c), value=str(item.get(c, "")), height=120)

        with st.expander("Editar Treinamento (training_*)", expanded=True):
            for c in training_cols:
                edited[c] = st.text_area(prettify_label(c), value=str(item.get(c, "")), height=120)

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
