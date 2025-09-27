import os
import math
import pandas as pd
import streamlit as st
import psycopg2
from openpyxl import load_workbook
from dotenv import load_dotenv
from google.cloud import vision
import re
import base64

# ---- الإعدادات العامة ----
load_dotenv()
USERNAME = "admin"
PASSWORD = "Moraqip@123"

st.set_page_config(page_title="المراقب الذكي", layout="wide")

# ---- Google Vision ----
def setup_google_vision():
    try:
        key_b64 = st.secrets["GOOGLE_VISION_KEY_B64"]
        key_bytes = base64.b64decode(key_b64)
        with open("google_vision.json", "wb") as f:
            f.write(key_bytes)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_vision.json"
        return vision.ImageAnnotatorClient()
    except Exception as e:
        st.error(f"❌ لم يتم تحميل مفتاح Google Vision: {e}")
        return None

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

# ---- تحويل الجنس ----
def map_gender(x):
    try:
        val = int(float(x))
        return "F" if val == 1 else "M"
    except:
        return "M"

# ---- دالة لتغيير أسماء الأعمدة للعرض ----
def rename_columns(df):
    return df.rename(columns={
        "رقم الناخب": "voter_no",
        "الاسم الثلاثي": "full_name",
        "الجنس": "gender",
        "هاتف": "phone",
        "رقم العائلة": "family_number",
        "اسم مركز الاقتراع": "polling_center_name",
        "رقم مركز الاقتراع": "polling_center_number",
        "اسم مركز التسجيل": "station_number"
    })

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

# ---- اختيار المدينة ----
st.sidebar.header("🌆 اختر المدينة")
city = st.sidebar.selectbox("المدينة", ["Bagdad", "Babil"])
TABLE_NAME = city

# ========================== الواجهة ==========================
st.title("📊 المراقب الذكي - البحث في سجلات الناخبين")

# ====== تبويبات ======
tab_browse, tab_single, tab_file, tab_ocr, tab_count = st.tabs(
    ["📄 تصفّح السجلات", "🔍 بحث برقم", "📂 رفع ملف Excel", "📸 OCR صور بطاقات", "📦 عدّ البطاقات"]
)

# ----------------------------------------------------------------------------- #
# 📊 بحث متقدم عبر مراكز التسجيل / الاقتراع + فلاتر إضافية
# ----------------------------------------------------------------------------- #
tab_search, tab_single, tab_file, tab_ocr, tab_count = st.tabs(
    ["🏫 بحث بالمراكز والفلاتر", "🔍 بحث برقم", "📂 رفع ملف Excel", "📸 OCR صور بطاقات", "📦 عدّ البطاقات"]
)

with tab_search:
    st.subheader("🏫 البحث حسب المراكز + فلاتر إضافية")

    try:
        conn = get_conn()
        with conn.cursor() as cur:
            # مراكز الاقتراع
            cur.execute(f'SELECT DISTINCT "اسم مركز الاقتراع", "رقم مركز الاقتراع" FROM "{TABLE_NAME}" ORDER BY "اسم مركز الاقتراع";')
            polling_centers = cur.fetchall()

            # مراكز التسجيل
            cur.execute(f'SELECT DISTINCT "اسم مركز التسجيل", "رقم مركز التسجيل" FROM "{TABLE_NAME}" ORDER BY "اسم مركز التسجيل";')
            registration_centers = cur.fetchall()
        conn.close()

        # ---- واجهة الفلاتر ----
        col1, col2 = st.columns(2)
        with col1:
            selected_polling = st.selectbox(
                "🏫 اختر مركز الاقتراع",
                options=[""] + [f"{name} ({num})" for name, num in polling_centers],
                index=0
            )
        with col2:
            selected_registration = st.selectbox(
                "📝 اختر مركز التسجيل",
                options=[""] + [f"{name} ({num})" for name, num in registration_centers],
                index=0
            )

        colf1, colf2, colf3 = st.columns(3)
        with colf1:
            phone_filter = st.text_input("📱 رقم الهاتف")
        with colf2:
            family_filter = st.text_input("👨‍👩‍👧‍👦 رقم العائلة")
        with colf3:
            gender_filter = st.selectbox("⚧ الجنس", ["", "ذكر", "أنثى"])

        page_size = st.selectbox("عدد الصفوف", [10, 20, 50, 100], index=1)

        if st.button("🔎 بحث"):
            where_clauses, params = [], []

            if selected_polling:
                num = re.findall(r"\((\d+)\)", selected_polling)
                if num:
                    where_clauses.append('"رقم مركز الاقتراع" = %s')
                    params.append(num[0])

            if selected_registration:
                num = re.findall(r"\((\d+)\)", selected_registration)
                if num:
                    where_clauses.append('"رقم مركز التسجيل" = %s')
                    params.append(num[0])

            if phone_filter.strip():
                where_clauses.append('"هاتف" ILIKE %s')
                params.append(f"%{phone_filter.strip()}%")

            if family_filter.strip():
                where_clauses.append('"رقم العائلة"::text ILIKE %s')
                params.append(f"%{family_filter.strip()}%")

            if gender_filter:
                val = 1 if gender_filter == "أنثى" else 0
                where_clauses.append('"الجنس" = %s')
                params.append(val)

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            sql = f'''
                SELECT "المدينة","رقم الناخب","الاسم الثلاثي","رقم العائلة",
                       "رقم مركز التسجيل","اسم مركز التسجيل",
                       "رقم مركز الاقتراع","اسم مركز الاقتراع",
                       "الجنس","تاريخ الميلاد","هاتف"
                FROM "{TABLE_NAME}"
                {where_sql}
                LIMIT %s;
            '''
            params.append(page_size)

            conn = get_conn()
            df = pd.read_sql_query(sql, conn, params=params)
            conn.close()

            if not df.empty:
                # تحويل الجنس من 0/1 إلى نص
                df["الجنس"] = df["الجنس"].apply(lambda x: "أنثى" if str(x) == "1" else "ذكر")

                st.success(f"✅ تم العثور على {len(df)} سجل")
                st.dataframe(df, use_container_width=True, height=500)
            else:
                st.warning("⚠️ لم يتم العثور على نتائج")
    except Exception as e:
        st.error(f"❌ خطأ: {e}")

# ----------------------------------------------------------------------------- #
# 2) 🔍 البحث برقم واحد
# ----------------------------------------------------------------------------- #
with tab_single:
    st.subheader("🔍 البحث برقم الناخب")
    voter_input = st.text_input("ادخل رقم الناخب:")
    if st.button("بحث"):
        try:
            conn = get_conn()
            query = f"""
                SELECT * FROM "{TABLE_NAME}" WHERE "رقم الناخب" = %s
            """
            df = pd.read_sql_query(query, conn, params=(voter_input.strip(),))
            conn.close()

            if not df.empty:
                df = rename_columns(df)
                df["الجنس"] = df["gender"].apply(map_gender)
                st.dataframe(df, use_container_width=True, height=500)
            else:
                st.warning("⚠️ لم يتم العثور على نتائج")
        except Exception as e:
            st.error(f"❌ خطأ: {e}")

# ----------------------------------------------------------------------------- #
# 3) 📂 رفع ملف Excel (مع إيجاد الأرقام غير الموجودة)
# ----------------------------------------------------------------------------- #
with tab_file:
    st.subheader("📂 البحث باستخدام ملف Excel")
    uploaded_file = st.file_uploader("📤 ارفع ملف (رقم الناخب)", type=["xlsx"])
    if uploaded_file and st.button("🚀 تشغيل البحث"):
        try:
            voters_df = pd.read_excel(uploaded_file, engine="openpyxl")
            voter_col = "رقم الناخب" if "رقم الناخب" in voters_df.columns else voters_df.columns[0]
            voters_list = voters_df[voter_col].astype(str).tolist()

            conn = get_conn()
            placeholders = ",".join(["%s"] * len(voters_list))
            query = f"""
                SELECT * FROM "{TABLE_NAME}" WHERE "رقم الناخب" IN ({placeholders})
            """
            df = pd.read_sql_query(query, conn, params=voters_list)
            conn.close()

            if not df.empty:
                df = rename_columns(df)
                df["الجنس"] = df["gender"].apply(map_gender)

                df["رقم المندوب الرئيسي"] = ""
                df["الحالة"] = 0
                df["ملاحظة"] = ""

                # ✅ ترتيب الأعمدة للعرض
                df = df[["voter_no","full_name","gender","phone",
                         "family_number","polling_center_name","polling_center_number",
                         "station_number","رقم المندوب الرئيسي","الحالة","ملاحظة"]]

                # ✅ إيجاد الأرقام غير الموجودة
                found_numbers = set(df["voter_no"].astype(str).tolist())
                missing_numbers = [num for num in voters_list if num not in found_numbers]

                # عرض النتائج الموجودة
                st.dataframe(df, use_container_width=True, height=500)

                # ملف النتائج الموجودة
                output_file = "نتائج_البحث.xlsx"
                df.to_excel(output_file, index=False, engine="openpyxl")
                wb = load_workbook(output_file)
                wb.active.sheet_view.rightToLeft = True
                wb.save(output_file)
                with open(output_file, "rb") as f:
                    st.download_button("⬇️ تحميل النتائج", f,
                        file_name="نتائج_البحث.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                # عرض وتحميل الأرقام غير الموجودة
                if missing_numbers:
                    st.warning("⚠️ الأرقام التالية لم يتم العثور عليها في قاعدة البيانات:")
                    st.write(missing_numbers)

                    missing_df = pd.DataFrame(missing_numbers, columns=["الأرقام غير الموجودة"])
                    miss_file = "missing_numbers.xlsx"
                    missing_df.to_excel(miss_file, index=False, engine="openpyxl")
                    with open(miss_file, "rb") as f:
                        st.download_button("⬇️ تحميل الأرقام غير الموجودة", f,
                            file_name="الأرقام_غير_الموجودة.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.warning("⚠️ لا يوجد نتائج")
        except Exception as e:
            st.error(f"❌ خطأ: {e}")
# ----------------------------------------------------------------------------- #
# 4) 📸 OCR صور بطاقات
# ----------------------------------------------------------------------------- #
with tab_ocr:
    st.subheader("📸 استخراج رقم الناخب من الصور")

    # ---- استخراج الأرقام فقط ----
    st.markdown("### 🔎 استخراج الأرقام فقط (بدون البحث في قاعدة البيانات)")
    imgs_only = st.file_uploader(
        "📤 ارفع صور البطاقات",
        type=["jpg","jpeg","png"],
        accept_multiple_files=True,
        key="ocr_only"
    )
    if imgs_only and st.button("🚀 استخراج الأرقام فقط"):
        client = setup_google_vision()
        if client:
            clear_numbers, unclear_candidates, results = [], [], []

            for img in imgs_only:
                try:
                    content = img.read()
                    image = vision.Image(content=content)
                    response = client.text_detection(image=image)
                    texts = response.text_annotations
                    if texts:
                        full_text = texts[0].description
                        found_clear = re.findall(r"\b\d{6,10}\b", full_text)
                        if found_clear:
                            clear_numbers.extend(found_clear)
                            results.append({"filename": img.name, "content": img, "numbers": found_clear})
                except Exception as e:
                    st.warning(f"⚠️ خطأ في {img.name}: {e}")

            clear_numbers = list(dict.fromkeys(clear_numbers))
            if clear_numbers:
                st.success("✅ تم استخراج الأرقام")
                st.write(clear_numbers)

# ---- استخراج والبحث ----
    imgs = st.file_uploader(
        "📤 ارفع صور البطاقات (للاستخراج + البحث في القاعدة)",
        type=["jpg","jpeg","png"],
        accept_multiple_files=True,
        key="ocr_search"
    )
    if imgs and st.button("🚀 استخراج والبحث"):
        client = setup_google_vision()
        if client:
            all_voters, results = [], []
            for img in imgs:
                try:
                    content = img.read()
                    image = vision.Image(content=content)
                    response = client.text_detection(image=image)
                    texts = response.text_annotations
                    if texts:
                        numbers = re.findall(r"\b\d{6,10}\b", texts[0].description)
                        if numbers:
                            all_voters.extend(numbers)
                            results.append({"filename": img.name, "content": img, "numbers": numbers})
                except Exception as e:
                    st.warning(f"⚠️ خطأ في {img.name}: {e}")

            if all_voters:
                conn = get_conn()
                placeholders = ",".join(["%s"] * len(all_voters))
                query = f"""SELECT * FROM "{TABLE_NAME}" WHERE "رقم الناخب" IN ({placeholders})"""
                df = pd.read_sql_query(query, conn, params=all_voters)
                conn.close()

                if not df.empty:
                    df = rename_columns(df)
                    df["الجنس"] = df["gender"].apply(map_gender)
                    st.dataframe(df, use_container_width=True, height=500)
                else:
                    st.warning("⚠️ لا توجد نتائج")

# ----------------------------------------------------------------------------- #
# 5) 📦 عدّ البطاقات (أرقام 8 خانات) + بحث في القاعدة
# ----------------------------------------------------------------------------- #
with tab_count:
    st.subheader("📦 عدّ البطاقات (أرقام 8 خانات) — بحث في القاعدة")

    imgs_count = st.file_uploader(
        "📤 ارفع صور الصفحات (قد تحتوي عدة بطاقات)",
        type=["jpg","jpeg","png"],
        accept_multiple_files=True,
        key="ocr_count"
    )

    if imgs_count and st.button("🚀 عدّ البطاقات والبحث"):
        client = setup_google_vision()
        if client:
            all_numbers, number_to_files = [], {}
            for img in imgs_count:
                try:
                    content = img.read()
                    image = vision.Image(content=content)
                    response = client.text_detection(image=image)
                    texts = response.text_annotations
                    full_text = texts[0].description if texts else ""
                    found_numbers = re.findall(r"\b\d{8}\b", full_text)
                    for n in found_numbers:
                        all_numbers.append(n)
                        number_to_files.setdefault(n, set()).add(img.name)
                except Exception as e:
                    st.warning(f"⚠️ خطأ في {img.name}: {e}")

            unique_numbers = sorted(set(all_numbers))
            if unique_numbers:
                conn = get_conn()
                placeholders = ",".join(["%s"] * len(unique_numbers))
                query = f"""SELECT * FROM "{TABLE_NAME}" WHERE "رقم الناخب" IN ({placeholders})"""
                found_df = pd.read_sql_query(query, conn, params=unique_numbers)
                conn.close()

                if not found_df.empty:
                    found_df = rename_columns(found_df)
                    found_df["الجنس"] = found_df["gender"].apply(map_gender)
                    st.dataframe(found_df, use_container_width=True, height=400)

                # الأرقام المفقودة
                found_numbers_set = set(found_df["voter_no"].astype(str)) if not found_df.empty else set()
                missing = [n for n in unique_numbers if n not in found_numbers_set]
                if missing:
                    st.warning("⚠️ أرقام غير موجودة:")
                    st.write(missing)
