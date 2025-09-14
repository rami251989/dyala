import os
import math
import pandas as pd
import streamlit as st
import psycopg2
from openpyxl import load_workbook
from dotenv import load_dotenv

# ---- الإعدادات العامة / البيئة ----
load_dotenv()

USERNAME = "admin"
PASSWORD = "Moraqip@123"

st.set_page_config(page_title="المراقب الذكي", layout="wide")

# ---- اتصال قاعدة البيانات ----
def get_conn():
    return psycopg2.connect(
        dbname=os.environ.get("DB_NAME"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        host=os.environ.get("DB_HOST"),
        port=os.environ.get("DB_PORT"),
        sslmode=os.environ.get("DB_SSLMODE", "require")
    )

# ---- تسجيل الدخول ----
def login():
    st.markdown("## 🔑 تسجيل الدخول")
    u = st.text_input("👤 اسم المستخدم")
    p = st.text_input("🔒 كلمة المرور", type="password")
    if st.button("دخول"):
        if u == USERNAME and p == PASSWORD:
            st.session_state.logged_in = True
            st.success("✅ تسجيل الدخول ناجح")
        else:
            st.error("❌ اسم المستخدم أو كلمة المرور غير صحيحة")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login()
    st.stop()

# ========================== الواجهة بعد تسجيل الدخول ==========================
st.title("📊 المراقب الذكي - البحث في سجلات الناخبين")
st.markdown("سيتم البحث في قواعد البيانات باستخدام الذكاء الاصطناعي 🤖")

# ====== تبويبات: تصفح كل الداتابيس (Pagination) | بحث برقم | رفع ملف ======
tab_browse, tab_single, tab_file = st.tabs(["📄 تصفّح السجلات (Pagination)", "🔍 بحث برقم", "📂 رفع ملف Excel"])

# ---------------------------------------------------------------------------
# دالة لتحويل الجنس من 0/1 إلى M/F
def convert_gender(df):
    if "الجنس" in df.columns:
        df["الجنس"] = df["الجنس"].astype(str).map({
            "0": "M",
            "1": "F"
        }).fillna("")
    return df

# ---------------------------------------------------------------------------
# 1) 📄 تصفّح السجلات مع Pagination + فلاتر
# ---------------------------------------------------------------------------
with tab_browse:
    st.subheader("📄 تصفّح السجلات مع فلاتر")
    if "page" not in st.session_state:
        st.session_state.page = 1
    if "filters" not in st.session_state:
        st.session_state.filters = {"voter": "", "name": "", "center": ""}

    colf1, colf2, colf3, colf4 = st.columns([1,1,1,1])
    with colf1:
        voter_filter = st.text_input("🔢 رقم الناخب يحتوي على:", value=st.session_state.filters["voter"])
    with colf2:
        name_filter = st.text_input("🧑‍💼 الاسم يحتوي على:", value=st.session_state.filters["name"])
    with colf3:
        center_filter = st.text_input("🏫 مركز الاقتراع يحتوي على:", value=st.session_state.filters["center"])
    with colf4:
        page_size = st.selectbox("عدد الصفوف/صفحة", [10, 20, 50, 100], index=1)

    col_apply, col_reset = st.columns([1,1])
    apply_clicked = col_apply.button("تطبيق الفلاتر 🔎")
    reset_clicked = col_reset.button("إعادة ضبط ↩️")

    if apply_clicked:
        st.session_state.filters = {
            "voter": voter_filter.strip(),
            "name": name_filter.strip(),
            "center": center_filter.strip(),
        }
        st.session_state.page = 1

    if reset_clicked:
        st.session_state.filters = {"voter": "", "name": "", "center": ""}
        voter_filter = name_filter = center_filter = ""
        st.session_state.page = 1

    where_clauses = []
    params = []

    if st.session_state.filters["voter"]:
        where_clauses.append('CAST("VoterNo" AS TEXT) ILIKE %s')
        params.append(f"%{st.session_state.filters['voter']}%")
    if st.session_state.filters["name"]:
        where_clauses.append('"الاسم الثلاثي" ILIKE %s')
        params.append(f"%{st.session_state.filters['name']}%")
    if st.session_state.filters["center"]:
        where_clauses.append('"اسم مركز الاقتراع" ILIKE %s')
        params.append(f"%{st.session_state.filters['center']}%")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    count_sql = f'SELECT COUNT(*) FROM voters {where_sql};'
    offset = (st.session_state.page - 1) * page_size
    data_sql = f'''
        SELECT
            "VoterNo",
            "الاسم الثلاثي",
            "الجنس",
            "هاتف",
            "رقم العائلة",
            "اسم مركز الاقتراع",
            "رقم مركز الاقتراع",
            "رقم المحطة"
        FROM voters
        {where_sql}
        ORDER BY "VoterNo" ASC
        LIMIT %s OFFSET %s;
    '''

    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            total_rows = cur.fetchone()[0]

        df = pd.read_sql_query(data_sql, conn, params=params + [page_size, offset])
        conn.close()

        if not df.empty:
            df = df.rename(columns={
                "VoterNo": "رقم الناخب",
                "الاسم الثلاثي": "الاسم",
                "الجنس": "الجنس",
                "هاتف": "رقم الهاتف",
                "رقم العائلة": "رقم العائلة",
                "اسم مركز الاقتراع": "مركز الاقتراع",
                "رقم مركز الاقتراع": "رقم مركز الاقتراع",
                "رقم المحطة": "رقم المحطة",
            })
            df = convert_gender(df)

        total_pages = max(1, math.ceil(total_rows / page_size))

        c1, c2, c3, c4, c5 = st.columns([1,1,2,1,1])
        with c1:
            prev = st.button("⬅️ السابق", use_container_width=True, disabled=(st.session_state.page <= 1))
        with c2:
            next_ = st.button("التالي ➡️", use_container_width=True, disabled=(st.session_state.page >= total_pages))
        with c3:
            st.markdown(f"<div style='text-align:center;font-weight:bold'>صفحة {st.session_state.page} من {total_pages} — إجمالي {total_rows} سجل</div>", unsafe_allow_html=True)
        with c4:
            jump = st.number_input("اذهب إلى صفحة", min_value=1, max_value=total_pages, value=st.session_state.page, step=1, label_visibility="collapsed")
        with c5:
            go = st.button("اذهب 🚀", use_container_width=True)

        if prev:
            st.session_state.page -= 1
            st.experimental_rerun()
        if next_:
            st.session_state.page += 1
            st.experimental_rerun()
        if go and jump != st.session_state.page:
            st.session_state.page = int(jump)
            st.experimental_rerun()

        st.dataframe(df, use_container_width=True, height=500)

        # تصدير الصفحة الحالية
        exp_col1, exp_col2 = st.columns([1,1])
        with exp_col1:
            st.download_button(
                "⬇️ تحميل الصفحة (CSV)",
                df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"voters_page_{st.session_state.page}.csv",
                mime="text/csv",
                use_container_width=True
            )
        with exp_col2:
            tmp_xlsx = f"voters_page_{st.session_state.page}.xlsx"
            df.to_excel(tmp_xlsx, index=False, engine="openpyxl")
            with open(tmp_xlsx, "rb") as f:
                st.download_button(
                    "⬇️ تحميل الصفحة (Excel)",
                    f,
                    file_name=tmp_xlsx,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

    except Exception as e:
        st.error(f"❌ خطأ أثناء التصفح: {e}")

# ---------------------------------------------------------------------------
# 2) 🔍 البحث برقم واحد
# ---------------------------------------------------------------------------
with tab_single:
    st.subheader("🔍 البحث برقم الناخب")
    voter_input = st.text_input("ادخل رقم الناخب:")
    if st.button("بحث"):
        if voter_input.strip() != "":
            try:
                conn = get_conn()
                query = """
                    SELECT 
                        "VoterNo",
                        "الاسم الثلاثي",
                        "الجنس",
                        "هاتف",
                        "رقم العائلة",
                        "اسم مركز الاقتراع",
                        "رقم مركز الاقتراع",
                        "رقم المحطة"
                    FROM voters
                    WHERE "VoterNo" = %s
                """
                df = pd.read_sql_query(query, conn, params=(voter_input.strip(),))
                conn.close()

                if not df.empty:
                    df = df.rename(columns={
                        "VoterNo": "رقم الناخب",
                        "الاسم الثلاثي": "الاسم",
                        "الجنس": "الجنس",
                        "هاتف": "رقم الهاتف",
                        "رقم العائلة": "رقم العائلة",
                        "اسم مركز الاقتراع": "مركز الاقتراع",
                        "رقم مركز الاقتراع": "رقم مركز الاقتراع",
                        "رقم المحطة": "رقم المحطة"
                    })
                    df = convert_gender(df)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.warning("⚠️ لم يتم العثور على نتائج لهذا الرقم")
            except Exception as e:
                st.error(f"❌ خطأ: {e}")
        else:
            st.warning("⚠️ الرجاء إدخال رقم الناخب")

# ---------------------------------------------------------------------------
# 3) 📂 البحث باستخدام ملف Excel
# ---------------------------------------------------------------------------
with tab_file:
    st.subheader("📂 البحث باستخدام ملف Excel")
    uploaded_voter_file = st.file_uploader("ارفع ملف الناخبين (يحتوي على VoterNo أو رقم الناخب)", type=["xlsx"])

    if uploaded_voter_file:
        if st.button("🚀 تشغيل البحث"):
            try:
                voters_df = pd.read_excel(uploaded_voter_file, engine="openpyxl")
                if "VoterNo" not in voters_df.columns and "رقم الناخب" not in voters_df.columns:
                    st.error("❌ ملف الناخبين يجب أن يحتوي على عمود VoterNo أو رقم الناخب")
                else:
                    voter_col = "VoterNo" if "VoterNo" in voters_df.columns else "رقم الناخب"
                    voters_list = voters_df[voter_col].astype(str).tolist()

                    conn = get_conn()
                    placeholders = ",".join(["%s"] * len(voters_list))
                    query = f"""
                        SELECT 
                            "VoterNo",
                            "الاسم الثلاثي",
                            "الجنس",
                            "هاتف",
                            "رقم العائلة",
                            "اسم مركز الاقتراع",
                            "رقم مركز الاقتراع",
                            "رقم المحطة"
                        FROM voters
                        WHERE "VoterNo" IN ({placeholders})
                    """
                    df = pd.read_sql_query(query, conn, params=voters_list)
                    conn.close()

                    if not df.empty:
                        df = df.rename(columns={
                            "VoterNo": "رقم الناخب",
                            "الاسم الثلاثي": "الاسم",
                            "الجنس": "الجنس",
                            "هاتف": "رقم الهاتف",
                            "رقم العائلة": "رقم العائلة",
                            "اسم مركز الاقتراع": "مركز الاقتراع",
                            "رقم مركز الاقتراع": "رقم مركز الاقتراع",
                            "رقم المحطة": "رقم المحطة"
                        })
                        df = convert_gender(df)

                        df["رقم المندوب الرئيسي"] = ""
                        df["الحالة"] = 0
                        df["ملاحظة"] = ""

                        df = df[
                            ["رقم الناخب", "الاسم", "الجنس", "رقم الهاتف",
                             "رقم العائلة", "مركز الاقتراع", "رقم مركز الاقتراع",
                             "رقم المحطة", "رقم المندوب الرئيسي", "الحالة", "ملاحظة"]
                        ]

                        output_file = "نتائج_البحث.xlsx"
                        df.to_excel(output_file, index=False, engine="openpyxl")

                        wb = load_workbook(output_file)
                        ws = wb.active
                        ws.sheet_view.rightToLeft = True
                        wb.save(output_file)

                        with open(output_file, "rb") as f:
                            st.download_button(
                                "⬇️ تحميل النتائج",
                                f,
                                file_name="نتائج_البحث.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    else:
                        st.warning("⚠️ لم يتم العثور على نتائج")

            except Exception as e:
                st.error(f"❌ خطأ: {e}")
