import os
import math
import pandas as pd
import streamlit as st
import psycopg2
from openpyxl import load_workbook
from dotenv import load_dotenv
import base64
import re

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

# ========================== اختيار المدينة ==========================
city = st.sidebar.selectbox("📍 اختر المدينة", ["Bagdad", "Babil"])
table_name = f"\"{city}\""

st.title(f"📊 المراقب الذكي - البحث في سجلات الناخبين ({city})")
# ====== تبويبات ======
tab_centers, tab_single, tab_file, tab_ocr, tab_count = st.tabs(
    ["🏫 بحث بالمراكز والفلاتر", "🔍 بحث برقم", "📂 رفع ملف Excel", "📸 OCR صور بطاقات", "📦 عدّ البطاقات"]
)

# ----------------------------------------------------------------------------- #
# 🏫 بحث بالمراكز والفلاتر
# ----------------------------------------------------------------------------- #
with tab_centers:
    st.subheader("🏫 البحث حسب المراكز + فلاتر إضافية")

    try:
        conn = get_conn()
        cur = conn.cursor()

        # جلب القيم المميزة للمراكز
        cur.execute(f'SELECT DISTINCT "اسم مركز الاقتراع" FROM {table_name} ORDER BY 1')
        polling_centers = [r[0] for r in cur.fetchall() if r[0]]

        cur.execute(f'SELECT DISTINCT "اسم مركز التسجيل" FROM {table_name} ORDER BY 1')
        reg_centers = [r[0] for r in cur.fetchall() if r[0]]

        conn.close()

        # DropDowns للمراكز
        selected_polling = st.selectbox("🏫 اختر مركز الاقتراع", [""] + polling_centers)
        selected_reg = st.selectbox("📝 اختر مركز التسجيل", [""] + reg_centers)

        # فلاتر إضافية
        phone_filter = st.text_input("📞 رقم الهاتف يحتوي على:")
        family_filter = st.text_input("👨‍👩‍👦 رقم العائلة:")
        gender_filter = st.radio("⚧ الجنس", ["", "ذكر", "أنثى"], horizontal=True)

        if st.button("🔎 بحث"):
            filters, params = [], []

            if selected_polling:
                filters.append('"اسم مركز الاقتراع" = %s')
                params.append(selected_polling)
            if selected_reg:
                filters.append('"اسم مركز التسجيل" = %s')
                params.append(selected_reg)
            if phone_filter:
                filters.append('"هاتف" ILIKE %s')
                params.append(f"%{phone_filter}%")
            if family_filter:
                filters.append('"رقم العائلة"::TEXT ILIKE %s')
                params.append(f"%{family_filter}%")
            if gender_filter:
                if gender_filter == "أنثى":
                    filters.append('"الجنس" = 1')
                elif gender_filter == "ذكر":
                    filters.append('"الجنس" = 0')

            where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

            query = f"""
                SELECT
                    "المدينة", "رقم الناخب", "الاسم الثلاثي", "رقم العائلة",
                    "رقم مركز التسجيل", "اسم مركز التسجيل",
                    "رقم مركز الاقتراع", "اسم مركز الاقتراع",
                    "الجنس", "تاريخ الميلاد", "هاتف"
                FROM {table_name}
                {where_sql}
                LIMIT 200;
            """

            conn = get_conn()
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()

            if not df.empty:
                df["الجنس"] = df["الجنس"].apply(lambda x: "أنثى" if str(x) == "1" else "ذكر")
                st.dataframe(df, use_container_width=True, height=500)
            else:
                st.warning("⚠️ لا توجد نتائج تطابق الفلاتر")
    except Exception as e:
        st.error(f"❌ خطأ أثناء تحميل المراكز: {e}")
# ----------------------------------------------------------------------------- #
# 🔍 البحث برقم الناخب
# ----------------------------------------------------------------------------- #
with tab_single:
    st.subheader("🔍 البحث برقم الناخب")

    voter_no = st.text_input("🆔 أدخل رقم الناخب")

    if st.button("بحث برقم", key="btn_voter"):
        if voter_no.strip():
            try:
                query = f"""
                    SELECT
                        "المدينة", "رقم الناخب", "الاسم الثلاثي", "رقم العائلة",
                        "رقم مركز التسجيل", "اسم مركز التسجيل",
                        "رقم مركز الاقتراع", "اسم مركز الاقتراع",
                        "الجنس", "تاريخ الميلاد", "هاتف"
                    FROM {table_name}
                    WHERE "رقم الناخب"::TEXT = %s
                    LIMIT 1;
                """

                conn = get_conn()
                df = pd.read_sql_query(query, conn, params=[voter_no.strip()])
                conn.close()

                if not df.empty:
                    df["الجنس"] = df["الجنس"].apply(lambda x: "أنثى" if str(x) == "1" else "ذكر")
                    st.table(df)
                else:
                    st.warning("⚠️ لم يتم العثور على الناخب")
            except Exception as e:
                st.error(f"❌ خطأ أثناء البحث: {e}")
        else:
            st.warning("⚠️ الرجاء إدخال رقم الناخب")
# ----------------------------------------------------------------------------- #
# 📂 رفع ملف Excel للبحث برقم الناخب
# ----------------------------------------------------------------------------- #
with tab_file:
    st.subheader("📂 رفع ملف Excel للبحث عن الناخبين")

    uploaded_file = st.file_uploader("📥 اختر ملف Excel يحتوي على أرقام الناخبين", type=["xlsx"])

    if uploaded_file is not None:
        try:
            excel_data = pd.read_excel(uploaded_file)
            if "رقم الناخب" not in excel_data.columns:
                st.error("❌ ملف Excel يجب أن يحتوي على عمود باسم (رقم الناخب)")
            else:
                voter_numbers = excel_data["رقم الناخب"].astype(str).tolist()

                query = f"""
                    SELECT
                        "المدينة", "رقم الناخب", "الاسم الثلاثي", "رقم العائلة",
                        "رقم مركز التسجيل", "اسم مركز التسجيل",
                        "رقم مركز الاقتراع", "اسم مركز الاقتراع",
                        "الجنس", "تاريخ الميلاد", "هاتف"
                    FROM {table_name}
                    WHERE "رقم الناخب"::TEXT = ANY(%s)
                """

                conn = get_conn()
                df = pd.read_sql_query(query, conn, params=[voter_numbers])
                conn.close()

                if not df.empty:
                    df["الجنس"] = df["الجنس"].apply(lambda x: "أنثى" if str(x) == "1" else "ذكر")
                    st.dataframe(df, use_container_width=True, height=500)

                    # تحميل النتائج كـ Excel
                    def convert_df(df):
                        return df.to_csv(index=False).encode("utf-8-sig")

                    st.download_button(
                        "⬇️ تحميل النتائج كملف CSV",
                        convert_df(df),
                        "results.csv",
                        "text/csv",
                        key="download-csv"
                    )
                else:
                    st.warning("⚠️ لم يتم العثور على أي نتائج")
        except Exception as e:
            st.error(f"❌ خطأ أثناء معالجة الملف: {e}")
# ----------------------------------------------------------------------------- #
# 📸 OCR صور بطاقات
# ----------------------------------------------------------------------------- #
with tab_ocr:
    st.subheader("📸 البحث عبر OCR من صورة بطاقة")

    ocr_file = st.file_uploader("📥 ارفع صورة البطاقة", type=["png", "jpg", "jpeg"])

    if ocr_file is not None:
        # ⚠️ هنا بدك تضيف دالة OCR حقيقية (Tesseract أو API خارجي)
        # أنا رح أعمل محاكاة: نستخرج رقم من اسم الملف فقط
        extracted_number = re.sub(r"\D", "", ocr_file.name)

        if extracted_number:
            st.info(f"🔍 تم استخراج رقم الناخب: {extracted_number}")

            query = f"""
                SELECT
                    "المدينة", "رقم الناخب", "الاسم الثلاثي", "رقم العائلة",
                    "رقم مركز التسجيل", "اسم مركز التسجيل",
                    "رقم مركز الاقتراع", "اسم مركز الاقتراع",
                    "الجنس", "تاريخ الميلاد", "هاتف"
                FROM {table_name}
                WHERE "رقم الناخب"::TEXT = %s
                LIMIT 1;
            """

            conn = get_conn()
            df = pd.read_sql_query(query, conn, params=[extracted_number])
            conn.close()

            if not df.empty:
                df["الجنس"] = df["الجنس"].apply(lambda x: "أنثى" if str(x) == "1" else "ذكر")
                st.table(df)
            else:
                st.warning("⚠️ لم يتم العثور على الناخب")
        else:
            st.error("❌ لم يتم التعرف على رقم الناخب من الصورة")
# ----------------------------------------------------------------------------- #
# 📦 عدّ البطاقات
# ----------------------------------------------------------------------------- #
with tab_count:
    st.subheader("📦 إحصائيات الناخبين")

    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        total = cur.fetchone()[0]

        cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE \"الجنس\" = 1")
        females = cur.fetchone()[0]

        cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE \"الجنس\" = 0")
        males = cur.fetchone()[0]

        conn.close()

        st.metric("👥 إجمالي الناخبين", total)
        st.metric("👩 عدد الإناث", females)
        st.metric("👨 عدد الذكور", males)
    except Exception as e:
        st.error(f"❌ خطأ أثناء جلب الإحصائيات: {e}")
