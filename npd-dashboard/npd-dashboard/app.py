"""
NPD-TEAM Operation Center
-------------------------
ระบบจัดการโปรเจกต์ทีม NPD พร้อมระบบล็อกอิน (สร้าง/จัดการผู้ใช้ได้)
และฐานข้อมูลเก็บบน Google Sheets (ทั้งตารางผู้ใช้ และตารางข้อมูลโปรเจกต์)

โครงสร้าง Google Sheet ที่ต้องมี (สร้างอัตโนมัติถ้ายังไม่มี):
  - แท็บ "Users": Username | FirstName | LastName | Email | Password | Roles
  - แท็บ "Data" : ID | ProjectName | Category | Owner | StartDate | Status
                   | Priority | Budget | Progress | Description | CreatedAt | UpdatedAt
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import streamlit_authenticator as stauth
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date

# ============================================================
# 1) PAGE CONFIG (ต้องมาก่อน Streamlit command อื่น ๆ)
# ============================================================
st.set_page_config(
    page_title="NPD-TEAM Dashboard",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 2) CONSTANTS
# ============================================================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
USERS_SHEET = "Users"
DATA_SHEET = "Data"
USERS_HEADER = ["Username", "FirstName", "LastName", "Email", "Password", "Roles"]
DATA_HEADER = [
    "ID", "ProjectName", "Category", "Owner", "StartDate", "Status",
    "Priority", "Budget", "Progress", "Description", "CreatedAt", "UpdatedAt",
]
STATUS_OPTIONS = ["ยังไม่เริ่ม", "วางแผน", "กำลังดำเนินการ", "เสร็จสิ้น"]
PRIORITY_OPTIONS = ["ปานกลาง", "สูง", "ด่วนที่สุด"]
CATEGORY_OPTIONS = ["การพัฒนาผลิตภัณฑ์", "การตลาด", "การวิจัย", "อื่นๆ"]

STATUS_COLORS = {
    "ยังไม่เริ่ม": "#94a3b8",
    "วางแผน": "#38bdf8",
    "กำลังดำเนินการ": "#fbbf24",
    "เสร็จสิ้น": "#34d399",
}
PRIORITY_COLORS = {"ปานกลาง": "#38bdf8", "สูง": "#fb923c", "ด่วนที่สุด": "#f43f5e"}

# ============================================================
# 3) STYLE
# ============================================================
st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}

.stApp {
    background: radial-gradient(circle at top left, #1b1130 0%, #0f0c1d 45%, #0a0912 100%);
}

.hero-banner {
    background: linear-gradient(120deg, #ff5858 0%, #ff8a3d 45%, #f83737 100%);
    border-radius: 18px;
    padding: 28px 32px;
    margin-bottom: 22px;
    box-shadow: 0 10px 30px rgba(248, 55, 55, 0.25);
}
.hero-banner h1 {
    color: white;
    margin: 0;
    font-size: 30px;
    font-weight: 800;
}
.hero-banner p {
    color: rgba(255,255,255,0.9);
    margin: 4px 0 0 0;
}

.glass-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 18px 20px;
    backdrop-filter: blur(6px);
}

.stButton>button, .stFormSubmitButton>button {
    background: linear-gradient(90deg, #ff5858 0%, #f83737 100%);
    color: white;
    border-radius: 10px;
    font-weight: 600;
    border: none;
    padding: 0.5rem 1.1rem;
    box-shadow: 0 4px 10px rgba(248, 55, 55, 0.3);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.stButton>button:hover, .stFormSubmitButton>button:hover {
    background: linear-gradient(90deg, #ff3333 0%, #e62e2e 100%);
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(248, 55, 55, 0.45);
}

[data-testid="stMetric"] {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 14px 16px;
}

.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
    color: #0a0912;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# 4) HELPERS
# ============================================================
def _to_plain(obj):
    """Recursively turn Streamlit's read-only secrets mapping into plain dict/list."""
    if hasattr(obj, "items"):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    return obj


def require_secret(path, label):
    node = st.secrets
    try:
        for key in path:
            node = node[key]
        return node
    except Exception:
        st.markdown('<div class="hero-banner"><h1>⚙️ ต้องตั้งค่า Secrets ก่อนใช้งาน</h1></div>', unsafe_allow_html=True)
        st.error(
            f"ไม่พบการตั้งค่า **{label}** ใน `secrets.toml`\n\n"
            "กรุณาดูตัวอย่างไฟล์ `.streamlit/secrets.toml.example` และ README.md "
            "ประกอบการตั้งค่า Service Account และ Google Sheet ID"
        )
        st.stop()


# ============================================================
# 5) GOOGLE SHEETS CONNECTION
# ============================================================
@st.cache_resource(show_spinner=False)
def get_gs_client():
    info = _to_plain(require_secret(["gcp_service_account"], "gcp_service_account"))
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def get_spreadsheet():
    sheet_id = require_secret(["gsheet", "sheet_id"], "gsheet.sheet_id")
    client = get_gs_client()
    try:
        return client.open_by_key(sheet_id)
    except Exception as e:
        st.markdown('<div class="hero-banner"><h1>❌ เชื่อมต่อ Google Sheet ไม่สำเร็จ</h1></div>', unsafe_allow_html=True)
        st.error(
            f"รายละเอียด: {e}\n\n"
            "ตรวจสอบว่า:\n"
            "1) Sheet ID ถูกต้อง\n"
            "2) แชร์ชีตให้กับอีเมลของ Service Account (client_email) เป็นสิทธิ์ **Editor**\n"
            "3) เปิดใช้งาน Google Sheets API และ Google Drive API ในโปรเจกต์ GCP แล้ว"
        )
        st.stop()


def get_or_create_worksheet(name, header):
    sh = get_spreadsheet()
    try:
        ws = sh.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows=1000, cols=len(header) + 2)
        ws.append_row(header)
        return ws
    existing = ws.row_values(1)
    if not existing:
        ws.append_row(header)
    return ws


@st.cache_data(ttl=20, show_spinner=False)
def load_users_df():
    ws = get_or_create_worksheet(USERS_SHEET, USERS_HEADER)
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    for col in USERS_HEADER:
        if col not in df.columns:
            df[col] = ""
    if not df.empty:
        df["Username"] = df["Username"].astype(str).str.strip()
    return df[df["Username"] != ""] if not df.empty else df


@st.cache_data(ttl=15, show_spinner=False)
def load_data_df():
    ws = get_or_create_worksheet(DATA_SHEET, DATA_HEADER)
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    for col in DATA_HEADER:
        if col not in df.columns:
            df[col] = ""
    if not df.empty:
        df["Budget"] = pd.to_numeric(df["Budget"], errors="coerce").fillna(0)
        df["Progress"] = pd.to_numeric(df["Progress"], errors="coerce").fillna(0).clip(0, 100)
    return df


def append_user_row(row: dict):
    ws = get_or_create_worksheet(USERS_SHEET, USERS_HEADER)
    ws.append_row([str(row.get(c, "")) for c in USERS_HEADER])
    load_users_df.clear()


def update_user_cell(username, column, value):
    ws = get_or_create_worksheet(USERS_SHEET, USERS_HEADER)
    cell = ws.find(username, in_column=1)
    if cell:
        col_idx = USERS_HEADER.index(column) + 1
        ws.update_cell(cell.row, col_idx, str(value))
    load_users_df.clear()


def append_data_row(row: dict):
    ws = get_or_create_worksheet(DATA_SHEET, DATA_HEADER)
    ws.append_row([str(row.get(c, "")) for c in DATA_HEADER])
    load_data_df.clear()


def overwrite_data_sheet(df: pd.DataFrame):
    ws = get_or_create_worksheet(DATA_SHEET, DATA_HEADER)
    ws.clear()
    ws.append_row(DATA_HEADER)
    if not df.empty:
        clean = df.copy()
        for col in DATA_HEADER:
            if col not in clean.columns:
                clean[col] = ""
        ws.append_rows(clean[DATA_HEADER].astype(str).values.tolist())
    load_data_df.clear()


def next_project_id(df: pd.DataFrame) -> str:
    if df.empty:
        return "P001"
    nums = []
    for x in df["ID"].astype(str):
        digits = "".join(ch for ch in x if ch.isdigit())
        if digits:
            nums.append(int(digits))
    n = (max(nums) + 1) if nums else 1
    return f"P{n:03d}"


def build_credentials(users_df: pd.DataFrame) -> dict:
    creds = {"usernames": {}}
    for _, r in users_df.iterrows():
        uname = str(r.get("Username", "")).strip()
        if not uname:
            continue
        roles_raw = str(r.get("Roles", "")).strip()
        roles = [x.strip() for x in roles_raw.split(",") if x.strip()] or ["member"]
        creds["usernames"][uname] = {
            "email": r.get("Email", ""),
            "first_name": r.get("FirstName", "") or uname,
            "last_name": r.get("LastName", ""),
            "password": r.get("Password", ""),
            "roles": roles,
        }
    return creds


def badge(text, color):
    return f'<span class="badge" style="background:{color}">{text}</span>'


# ============================================================
# 6) BOOTSTRAP: สร้างแอดมินคนแรกถ้ายังไม่มีผู้ใช้งานเลย
# ============================================================
users_df = load_users_df()

if users_df.empty:
    st.markdown(
        '<div class="hero-banner"><h1>⚡ NPD Operation Center</h1>'
        '<p>ตั้งค่าเริ่มต้น: สร้างบัญชีผู้ดูแลระบบ (Admin) คนแรกของทีม</p></div>',
        unsafe_allow_html=True,
    )
    st.info("ยังไม่มีผู้ใช้งานในระบบ กรุณาสร้างบัญชีแอดมินคนแรกเพื่อเริ่มใช้งาน")
    with st.form("bootstrap_admin"):
        c1, c2 = st.columns(2)
        with c1:
            b_username = st.text_input("Username *")
            b_first = st.text_input("ชื่อ")
            b_email = st.text_input("อีเมล")
        with c2:
            b_password = st.text_input("รหัสผ่าน *", type="password")
            b_password2 = st.text_input("ยืนยันรหัสผ่าน *", type="password")
            b_last = st.text_input("นามสกุล")
        submitted = st.form_submit_button("🚀 สร้างบัญชีแอดมิน")

    if submitted:
        if not b_username.strip() or not b_password:
            st.error("กรุณากรอก Username และรหัสผ่านให้ครบถ้วน")
        elif b_password != b_password2:
            st.error("รหัสผ่านทั้งสองช่องไม่ตรงกัน")
        else:
            hashed = stauth.Hasher.hash(b_password)
            append_user_row({
                "Username": b_username.strip(),
                "FirstName": b_first.strip(),
                "LastName": b_last.strip(),
                "Email": b_email.strip(),
                "Password": hashed,
                "Roles": "admin",
            })
            st.success("สร้างบัญชีแอดมินสำเร็จ! กำลังโหลดหน้าเข้าสู่ระบบ...")
            st.rerun()
    st.stop()

# ============================================================
# 7) AUTHENTICATION
# ============================================================
cookie_cfg = _to_plain(st.secrets.get("cookie", {}))
cookie_name = cookie_cfg.get("name", "npd_team_cookie")
cookie_key = cookie_cfg.get("key", "npd_team_default_key_change_me")
cookie_expiry = cookie_cfg.get("expiry_days", 30)

credentials = build_credentials(users_df)

authenticator = stauth.Authenticate(
    credentials,
    cookie_name,
    cookie_key,
    cookie_expiry,
    auto_hash=False,  # รหัสผ่านใน Google Sheet ถูก hash ไว้แล้วเสมอ
)

if st.session_state.get("authentication_status") is not True:
    st.markdown(
        '<div class="hero-banner"><h1>⚡ NPD Operation Center</h1>'
        '<p>ระบบบริหารจัดการงานและข้อมูลภายในทีมอย่างมีประสิทธิภาพและทันสมัย</p></div>',
        unsafe_allow_html=True,
    )

try:
    authenticator.login(
        location="main",
        fields={"Form name": "เข้าสู่ระบบ NPD-TEAM", "Username": "ชื่อผู้ใช้",
                "Password": "รหัสผ่าน", "Login": "เข้าสู่ระบบ"},
    )
except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการเข้าสู่ระบบ: {e}")

auth_status = st.session_state.get("authentication_status")

if auth_status is False:
    st.error("😕 ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    st.stop()
elif auth_status is None:
    st.warning("กรุณากรอกชื่อผู้ใช้และรหัสผ่านเพื่อเข้าสู่ระบบ")
    st.stop()

# ---- ผ่านการล็อกอินแล้ว ----
username = st.session_state["username"]
name = st.session_state.get("name", username)
roles = st.session_state.get("roles") or credentials["usernames"].get(username, {}).get("roles", ["member"])
is_admin = any(r.lower() == "admin" for r in roles)

# ============================================================
# 8) SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown(f"### 👋 สวัสดี, {name}")
    role_label = "👑 ผู้ดูแลระบบ" if is_admin else "🙍 สมาชิกทีม"
    st.caption(role_label)
    authenticator.logout("🚪 ออกจากระบบ", "sidebar")
    st.markdown("---")

    st.markdown("### 🔎 ตัวกรองภาพรวม")
    status_filter = st.multiselect("สถานะ", STATUS_OPTIONS, default=STATUS_OPTIONS)
    priority_filter = st.multiselect("ความสำคัญ", PRIORITY_OPTIONS, default=PRIORITY_OPTIONS)
    st.markdown("---")

    with st.expander("🔑 เปลี่ยนรหัสผ่านของฉัน"):
        try:
            if authenticator.reset_password(
                username,
                location="sidebar",
                fields={"Form name": "เปลี่ยนรหัสผ่าน", "Current password": "รหัสผ่านปัจจุบัน",
                        "New password": "รหัสผ่านใหม่", "Repeat password": "ยืนยันรหัสผ่านใหม่",
                        "Reset": "บันทึก"},
            ):
                new_hash = credentials["usernames"][username]["password"]
                update_user_cell(username, "Password", new_hash)
                st.success("เปลี่ยนรหัสผ่านสำเร็จ")
        except Exception as e:
            st.error(str(e))

    st.info("💡 **Tips:** อัปเดตสถานะงานทุกสัปดาห์เพื่อภาพรวมที่เป็นปัจจุบัน")

# ============================================================
# 9) HEADER
# ============================================================
st.markdown(
    '<div class="hero-banner"><h1>⚡ NPD Operation Center</h1>'
    '<p>ระบบบริหารจัดการงานและข้อมูลภายในทีม — ข้อมูลถูกบันทึกลง Google Sheet แบบเรียลไทม์</p></div>',
    unsafe_allow_html=True,
)

data_df = load_data_df()
filtered_df = data_df[
    data_df["Status"].isin(status_filter) & data_df["Priority"].isin(priority_filter)
] if not data_df.empty else data_df

tab_names = ["✍️ บันทึกงานใหม่", "📋 ตารางงานทั้งหมด", "📊 Dashboard ภาพรวม", "🔎 ค้นหาขั้นสูง"]
if is_admin:
    tab_names.append("👥 จัดการผู้ใช้")
tabs = st.tabs(tab_names)

# ------------------------------------------------------------
# TAB 1: บันทึกงานใหม่
# ------------------------------------------------------------
with tabs[0]:
    st.subheader("✍️ บันทึกข้อมูลโปรเจกต์ใหม่")
    st.markdown("---")
    with st.form("entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2, gap="large")
        with col1:
            st.markdown("#### 📌 ข้อมูลเบื้องต้น")
            project_name = st.text_input("ชื่อโปรเจกต์ *", placeholder="ชื่อโปรเจกต์ NPD ที่ต้องการเพิ่ม...")
            category = st.selectbox("🏷️ หมวดหมู่", CATEGORY_OPTIONS)
            owner = st.text_input("👤 ผู้รับผิดชอบหลัก", value=name)
            start_date = st.date_input("📅 วันที่เริ่มต้น", value=date.today())
        with col2:
            st.markdown("#### 📊 รายละเอียดงาน")
            status = st.select_slider("🏁 สถานะปัจจุบัน", options=STATUS_OPTIONS)
            priority = st.select_slider("🚩 ระดับความสำคัญ", options=PRIORITY_OPTIONS)
            budget = st.number_input("💰 งบประมาณ (บาท)", min_value=0, step=1000)
            progress = st.slider("📈 ความคืบหน้า (%)", 0, 100, 0)
        st.markdown("---")
        description = st.text_area("📝 รายละเอียดเพิ่มเติม/หมายเหตุ", height=100)
        submit_button = st.form_submit_button("💾 บันทึกข้อมูล")

    if submit_button:
        if project_name.strip() == "":
            st.warning("⚠️ กรุณากรอกชื่อโปรเจกต์ก่อนทำการบันทึกครับ!")
        else:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            new_id = next_project_id(data_df)
            append_data_row({
                "ID": new_id,
                "ProjectName": project_name.strip(),
                "Category": category,
                "Owner": owner.strip(),
                "StartDate": start_date.strftime("%Y-%m-%d"),
                "Status": status,
                "Priority": priority,
                "Budget": budget,
                "Progress": progress,
                "Description": description.strip(),
                "CreatedAt": now,
                "UpdatedAt": now,
            })
            st.success(f"🎉 บันทึกโปรเจกต์ **'{project_name}'** (รหัส {new_id}) ลงระบบเรียบร้อยแล้ว!")
            st.rerun()

# ------------------------------------------------------------
# TAB 2: ตารางงานทั้งหมด (แก้ไข/ลบได้)
# ------------------------------------------------------------
with tabs[1]:
    st.subheader("📋 รายการข้อมูลโปรเจกต์ทั้งหมด")
    st.caption("แก้ไขค่าในตารางได้โดยตรง เพิ่ม/ลบแถวได้ แล้วกด 'บันทึกการเปลี่ยนแปลง' เพื่ออัปเดตลง Google Sheet")
    st.markdown("---")

    if data_df.empty:
        st.info("ยังไม่มีข้อมูลโปรเจกต์ — เริ่มเพิ่มได้ที่แท็บ 'บันทึกงานใหม่'")
    else:
        edited_df = st.data_editor(
            data_df,
            use_container_width=True,
            num_rows="dynamic",
            key="data_editor",
            column_config={
                "Status": st.column_config.SelectboxColumn("สถานะ", options=STATUS_OPTIONS),
                "Priority": st.column_config.SelectboxColumn("ความสำคัญ", options=PRIORITY_OPTIONS),
                "Category": st.column_config.SelectboxColumn("หมวดหมู่", options=CATEGORY_OPTIONS),
                "Progress": st.column_config.ProgressColumn("ความคืบหน้า", min_value=0, max_value=100, format="%d%%"),
                "Budget": st.column_config.NumberColumn("งบประมาณ (บาท)", format="%.0f"),
            },
        )
        if st.button("💾 บันทึกการเปลี่ยนแปลงลง Google Sheet"):
            edited_df["UpdatedAt"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            overwrite_data_sheet(edited_df)
            st.success("บันทึกการเปลี่ยนแปลงสำเร็จ")
            st.rerun()

# ------------------------------------------------------------
# TAB 3: Dashboard
# ------------------------------------------------------------
with tabs[2]:
    st.subheader("📈 Dashboard และสรุปภาพรวม")
    st.markdown("---")

    total = len(filtered_df)
    in_progress = int((filtered_df["Status"] == "กำลังดำเนินการ").sum()) if total else 0
    done = int((filtered_df["Status"] == "เสร็จสิ้น").sum()) if total else 0
    not_started = int((filtered_df["Status"] == "ยังไม่เริ่ม").sum()) if total else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("โปรเจกต์ทั้งหมด", total)
    c2.metric("กำลังดำเนินการ", in_progress)
    c3.metric("เสร็จสิ้นแล้ว", done)
    c4.metric("ยังไม่เริ่ม", not_started)

    st.markdown("---")
    if total == 0:
        st.info("ไม่มีข้อมูลตรงกับตัวกรองปัจจุบัน")
    else:
        cc1, cc2 = st.columns(2)
        with cc1:
            status_counts = filtered_df["Status"].value_counts().reset_index()
            status_counts.columns = ["สถานะ", "จำนวน"]
            fig1 = px.pie(
                status_counts, names="สถานะ", values="จำนวน", hole=0.5,
                color="สถานะ", color_discrete_map=STATUS_COLORS, title="สัดส่วนสถานะโปรเจกต์",
            )
            fig1.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig1, use_container_width=True)
        with cc2:
            prio_counts = filtered_df["Priority"].value_counts().reset_index()
            prio_counts.columns = ["ความสำคัญ", "จำนวน"]
            fig2 = px.bar(
                prio_counts, x="ความสำคัญ", y="จำนวน", color="ความสำคัญ",
                color_discrete_map=PRIORITY_COLORS, title="จำนวนงานตามระดับความสำคัญ",
            )
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig2, use_container_width=True)

        cc3, cc4 = st.columns(2)
        with cc3:
            budget_by_cat = filtered_df.groupby("Category", as_index=False)["Budget"].sum()
            fig3 = px.bar(
                budget_by_cat, x="Category", y="Budget", title="งบประมาณรวมตามหมวดหมู่ (บาท)",
                color="Category",
            )
            fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="white", showlegend=False)
            st.plotly_chart(fig3, use_container_width=True)
        with cc4:
            fig4 = px.bar(
                filtered_df.sort_values("Progress", ascending=True),
                x="Progress", y="ProjectName", orientation="h",
                title="ความคืบหน้ารายโปรเจกต์ (%)", color="Progress",
                color_continuous_scale=["#f43f5e", "#fbbf24", "#34d399"],
            )
            fig4.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig4, use_container_width=True)

# ------------------------------------------------------------
# TAB 4: ค้นหาขั้นสูง
# ------------------------------------------------------------
with tabs[3]:
    st.subheader("🔎 ค้นหาและกรองข้อมูลขั้นสูง")
    st.markdown("---")
    s1, s2 = st.columns(2)
    with s1:
        keyword = st.text_input("คำค้นหา (ชื่อโปรเจกต์ / ผู้รับผิดชอบ / รายละเอียด)")
        cat_filter = st.multiselect("หมวดหมู่", CATEGORY_OPTIONS, default=CATEGORY_OPTIONS)
    with s2:
        date_range = st.date_input("ช่วงวันที่เริ่มต้น", value=())
        min_progress = st.slider("ความคืบหน้าขั้นต่ำ (%)", 0, 100, 0)

    result_df = data_df.copy()
    if not result_df.empty:
        if keyword.strip():
            kw = keyword.strip().lower()
            mask = (
                result_df["ProjectName"].astype(str).str.lower().str.contains(kw)
                | result_df["Owner"].astype(str).str.lower().str.contains(kw)
                | result_df["Description"].astype(str).str.lower().str.contains(kw)
            )
            result_df = result_df[mask]
        result_df = result_df[result_df["Category"].isin(cat_filter)]
        result_df = result_df[result_df["Progress"] >= min_progress]
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start, end = date_range
            sd = pd.to_datetime(result_df["StartDate"], errors="coerce")
            result_df = result_df[(sd >= pd.Timestamp(start)) & (sd <= pd.Timestamp(end))]

    st.markdown(f"**พบทั้งหมด {len(result_df)} รายการ**")
    st.dataframe(
        result_df, use_container_width=True,
        column_config={
            "Progress": st.column_config.ProgressColumn("ความคืบหน้า", min_value=0, max_value=100, format="%d%%"),
            "Budget": st.column_config.NumberColumn("งบประมาณ (บาท)", format="%.0f"),
        },
    )
    if not result_df.empty:
        st.download_button(
            "⬇️ ดาวน์โหลดผลการค้นหาเป็น CSV",
            result_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="npd_search_results.csv",
            mime="text/csv",
        )

# ------------------------------------------------------------
# TAB 5: จัดการผู้ใช้ (Admin only)
# ------------------------------------------------------------
if is_admin:
    with tabs[4]:
        st.subheader("👥 จัดการผู้ใช้งานระบบ")
        st.markdown("---")

        st.markdown("#### รายชื่อผู้ใช้งานทั้งหมด")
        display_df = users_df[["Username", "FirstName", "LastName", "Email", "Roles"]]
        st.dataframe(display_df, use_container_width=True)

        st.markdown("---")
        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("#### ➕ เพิ่มผู้ใช้งานใหม่")
            try:
                email_new, username_new, name_new = authenticator.register_user(
                    location="main",
                    pre_authorized=None,
                    captcha=False,
                    password_hint=False,
                    roles=["member"],
                    fields={"Form name": "สมัครสมาชิกใหม่", "Email": "อีเมล", "Username": "ชื่อผู้ใช้",
                            "Password": "รหัสผ่าน", "Repeat password": "ยืนยันรหัสผ่าน",
                            "Password hint": "คำใบ้รหัสผ่าน", "Captcha": "Captcha", "Register": "สมัครสมาชิก"},
                )
                if email_new:
                    new_user = credentials["usernames"].get(username_new, {})
                    append_user_row({
                        "Username": username_new,
                        "FirstName": new_user.get("first_name", ""),
                        "LastName": new_user.get("last_name", ""),
                        "Email": email_new,
                        "Password": new_user.get("password", ""),
                        "Roles": ",".join(new_user.get("roles", ["member"])),
                    })
                    st.success(f"เพิ่มผู้ใช้งาน '{username_new}' สำเร็จ")
                    st.rerun()
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาด: {e}")

        with col_b:
            st.markdown("#### 🔧 เปลี่ยนสิทธิ์ผู้ใช้งาน")
            if not users_df.empty:
                sel_user = st.selectbox("เลือกผู้ใช้งาน", users_df["Username"].tolist())
                new_role = st.selectbox("สิทธิ์ใหม่", ["member", "admin"])
                if st.button("บันทึกสิทธิ์"):
                    if sel_user == username and new_role != "admin":
                        st.error("ไม่สามารถถอดสิทธิ์แอดมินของบัญชีตัวเองได้ ให้แอดมินคนอื่นดำเนินการแทน")
                    else:
                        update_user_cell(sel_user, "Roles", new_role)
                        st.success(f"เปลี่ยนสิทธิ์ของ '{sel_user}' เป็น '{new_role}' แล้ว")
                        st.rerun()
