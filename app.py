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
import cv2
import numpy as np
from PIL import Image
import io
import tempfile

# ---- الإعدادات العامة / البيئة ----
load_dotenv()

USERNAME = "admin"
PASSWORD = "Moraqip@123"

st.set_page_config(page_title="المراقب الذكي", layout="wide")

# ---- إعداد Google Vision من secrets ----
def setup_google_vision():
    try:
        key_b64 = st.secrets["GOOGLE_VISION_KEY_B64"]
        key_bytes = base64.b64decode(key_b64)
        with open("google_vision.json", "wb") as f:
            f.write(key_bytes)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_vision.json"
        return vision.ImageAnnotatorClient()
    except Exception as e:
        st.error(f"❌ لم يتم تحميل مفتاح Google Vision بشكل صحيح: {e}")
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

# ---- دالة تحويل الجنس ----
def map_gender(x):
    try:
        val = int(float(x))
        return "F" if val == 1 else "M"
    except:
        return "M"
# ---- تسجيل الدخول ----
# ---- تسجيل الدخول ----
def login():
    st.markdown(
        """
        <style>
        .login-container {
            display: flex;
            justify-content: center;
            align-items: flex-start; /* يرفع الصندوق لفوق */
            height: 100vh;
            padding-top: 10vh;       /* مسافة من فوق */
        }
        .login-box {
            background: #ffffff;
            padding: 1.5rem 2rem;
            border-radius: 12px;
            box-shadow: 0px 2px 12px rgba(0,0,0,0.1);
            text-align: center;
            width: 300px;
        }
        .stTextInput>div>div>input {
            text-align: center;
            font-size: 14px;
            height: 35px;
        }
        .stButton button {
            background: linear-gradient(90deg, #4e73df, #1cc88a);
            color: white;
            border-radius: 6px;
            padding: 0.4rem 0.8rem;
            font-size: 14px;
            font-weight: bold;
            transition: 0.2s;
            width: 100%;
        }
        .stButton button:hover {
            background: linear-gradient(90deg, #1cc88a, #4e73df);
            transform: scale(1.02);
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown('<div class="login-container"><div class="login-box">', unsafe_allow_html=True)

    st.markdown("### 🔑 تسجيل الدخول")
    u = st.text_input("👤 اسم المستخدم", key="login_user")
    p = st.text_input("🔒 كلمة المرور", type="password", key="login_pass")

    # ✅ كبسة واحدة تكفي
    login_btn = st.button("🚀 دخول", key="login_btn")
    if login_btn:
        if u == USERNAME and p == PASSWORD:
            st.session_state.logged_in = True
            st.rerun()   # إعادة تحميل الصفحة مباشرة
        else:
            st.error("❌ اسم المستخدم أو كلمة المرور غير صحيحة")

    st.markdown('</div></div>', unsafe_allow_html=True)


# ---- تحقق من حالة الجلسة ----
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login()
    st.stop()

# ========================== الواجهة بعد تسجيل الدخول ==========================
st.title("📊 بغداد - البحث في سجلات الناخبين")
st.markdown("سيتم البحث في قواعد البيانات باستخدام الذكاء الاصطناعي 🤖")

# ====== تبويبات ======
tab_browse, tab_single, tab_file, tab_count, tab_check, tab_count_custom = st.tabs(
    ["📄 تصفّح السجلات", "🔍 بحث برقم", "📂 رفع ملف Excel", "📦 عدّ البطاقات", "🧾 التحقق من المعلومات", "🧮 تحليل البيانات (COUNT)"]
)
# ----------------------------------------------------------------------------- #
# 1) 📄 تصفّح السجلات
# ----------------------------------------------------------------------------- #
with tab_browse:
    st.subheader("📄 تصفّح السجلات مع فلاتر")

    if "page" not in st.session_state:
        st.session_state.page = 1
    if "filters" not in st.session_state:
        st.session_state.filters = {"voter": "", "name": "", "center": ""}

    colf1, colf2, colf3, colf4 = st.columns([1,1,1,1])
    with colf1:
        voter_filter = st.text_input("🔢 رقم الناخب:", value=st.session_state.filters["voter"])
    with colf2:
        name_filter = st.text_input("🧑‍💼 الاسم:", value=st.session_state.filters["name"])
    with colf3:
        center_filter = st.text_input("🏫 مركز الاقتراع:", value=st.session_state.filters["center"])
    with colf4:
        page_size = st.selectbox("عدد الصفوف", [10, 20, 50, 100], index=1)

    if st.button("🔎 تطبيق الفلاتر"):
        st.session_state.filters = {
            "voter": voter_filter.strip(),
            "name": name_filter.strip(),
            "center": center_filter.strip(),
        }
        st.session_state.page = 1

    # --- بناء شروط البحث ---
    where_clauses, params = [], []
    if st.session_state.filters["voter"]:
        where_clauses.append('CAST("رقم الناخب" AS TEXT) ILIKE %s')
        params.append(f"%{st.session_state.filters['voter']}%")
    if st.session_state.filters["name"]:
        where_clauses.append('"الاسم الثلاثي" ILIKE %s')
        params.append(f"%{st.session_state.filters['name']}%")
    if st.session_state.filters["center"]:
        where_clauses.append('"اسم مركز الاقتراع" ILIKE %s')
        params.append(f"%{st.session_state.filters['center']}%")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    count_sql = f'SELECT COUNT(*) FROM "Bagdad" {where_sql};'
    offset = (st.session_state.page - 1) * page_size
    data_sql = f'''
        SELECT
            "رقم الناخب","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
            "اسم مركز الاقتراع","رقم مركز الاقتراع",
            "المدينة","رقم مركز التسجيل","اسم مركز التسجيل","تاريخ الميلاد"
        FROM "Bagdad"
        {where_sql}
        ORDER BY "رقم الناخب" ASC
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
                "رقم الناخب": "رقم الناخب",
                "الاسم الثلاثي": "الاسم",
                "الجنس": "الجنس",
                "هاتف": "رقم الهاتف",
                "رقم العائلة": "رقم العائلة",
                "اسم مركز الاقتراع": "مركز الاقتراع",
                "رقم مركز الاقتراع": "رقم مركز الاقتراع",
                "المدينة": "المدينة",
                "رقم مركز التسجيل": "رقم مركز التسجيل",
                "اسم مركز التسجيل": "اسم مركز التسجيل",
                "تاريخ الميلاد": "تاريخ الميلاد"
            })
            df["الجنس"] = df["الجنس"].apply(map_gender)

        total_pages = max(1, math.ceil(total_rows / page_size))

        # ✅ عرض النتائج
        st.dataframe(df, use_container_width=True, height=500)

        c1, c2, c3 = st.columns([1,2,1])
        with c1:
            if st.button("⬅️ السابق", disabled=(st.session_state.page <= 1)):
                st.session_state.page -= 1
                st.experimental_rerun()
        with c2:
            st.markdown(f"<div style='text-align:center;font-weight:bold'>صفحة {st.session_state.page} من {total_pages}</div>", unsafe_allow_html=True)
        with c3:
            if st.button("التالي ➡️", disabled=(st.session_state.page >= total_pages)):
                st.session_state.page += 1
                st.experimental_rerun()

    except Exception as e:
        st.error(f"❌ خطأ أثناء التصفح: {e}")
# ----------------------------------------------------------------------------- #
# 2) 🔍 البحث برقم واحد
# ----------------------------------------------------------------------------- #
with tab_single:
    st.subheader("🔍 البحث برقم الناخب")
    voter_input = st.text_input("ادخل رقم الناخب:")
    if st.button("بحث"):
        try:
            conn = get_conn()
            query = """
                SELECT "رقم الناخب","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                       "اسم مركز الاقتراع","رقم مركز الاقتراع",
                       "المدينة","رقم مركز التسجيل","اسم مركز التسجيل","تاريخ الميلاد"
                FROM "Bagdad" WHERE "رقم الناخب" LIKE %s
            """
            df = pd.read_sql_query(query, conn, params=(voter_input.strip(),))
            conn.close()

            if not df.empty:
                df = df.rename(columns={
                    "رقم الناخب": "رقم الناخب",
                    "الاسم الثلاثي": "الاسم",
                    "الجنس": "الجنس",
                    "هاتف": "رقم الهاتف",
                    "رقم العائلة": "رقم العائلة",
                    "اسم مركز الاقتراع": "مركز الاقتراع",
                    "رقم مركز الاقتراع": "رقم مركز الاقتراع",
                    "المدينة": "المدينة",
                    "رقم مركز التسجيل": "رقم مركز التسجيل",
                    "اسم مركز التسجيل": "اسم مركز التسجيل",
                    "تاريخ الميلاد": "تاريخ الميلاد"
                })
                df["الجنس"] = df["الجنس"].apply(map_gender)

                st.dataframe(df, use_container_width=True, height=500)
            else:
                st.warning("⚠️ لم يتم العثور على نتائج")
        except Exception as e:
            st.error(f"❌ خطأ: {e}")
# ----------------------------------------------------------------------------- #
# 3) 📂 رفع ملف Excel (معدل مع الأرقام غير الموجودة)
# ----------------------------------------------------------------------------- #
with tab_file:
    st.subheader("📂 البحث باستخدام ملف Excel")
    uploaded_file = st.file_uploader("📤 ارفع ملف (رقم الناخب)", type=["xlsx"])
    if uploaded_file and st.button("🚀 تشغيل البحث"):
        try:
            voters_df = pd.read_excel(uploaded_file, engine="openpyxl")
            voter_col = "رقم الناخب" if "رقم الناخب" in voters_df.columns else "VoterNo"
            voters_list = voters_df[voter_col].astype(str).tolist()

            conn = get_conn()
            placeholders = ",".join(["%s"] * len(voters_list))
            query = f"""
                SELECT "رقم الناخب","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                       "اسم مركز الاقتراع","رقم مركز الاقتراع",
                       "المدينة","رقم مركز التسجيل","اسم مركز التسجيل","تاريخ الميلاد"
                FROM "Bagdad" WHERE "رقم الناخب" IN ({placeholders})
            """
            df = pd.read_sql_query(query, conn, params=voters_list)
            conn.close()

            if not df.empty:
                df = df.rename(columns={
                    "رقم الناخب": "رقم الناخب",
                    "الاسم الثلاثي": "الاسم",
                    "الجنس": "الجنس",
                    "هاتف": "رقم الهاتف",
                    "رقم العائلة": "رقم العائلة",
                    "اسم مركز الاقتراع": "مركز الاقتراع",
                    "رقم مركز الاقتراع": "رقم مركز الاقتراع",
                    "المدينة": "المدينة",
                    "رقم مركز التسجيل": "رقم مركز التسجيل",
                    "اسم مركز التسجيل": "اسم مركز التسجيل",
                    "تاريخ الميلاد": "تاريخ الميلاد"
                })
                df["الجنس"] = df["الجنس"].apply(map_gender)

                df["رقم المندوب الرئيسي"] = ""
                df["الحالة"] = 0
                df["ملاحظة"] = ""
                df["رقم المحطة"] = 1

                df = df[["رقم الناخب","الاسم","الجنس","رقم الهاتف",
                         "رقم العائلة","مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة",
                         "رقم المندوب الرئيسي","الحالة","ملاحظة"]]

                # ✅ إيجاد الأرقام غير الموجودة
                found_numbers = set(df["رقم الناخب"].astype(str).tolist())
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
# 5) 📦 عدّ البطاقات (أرقام 8 خانات) + بحث في القاعدة + قائمة الأرقام غير الموجودة
# ----------------------------------------------------------------------------- #
with tab_count:
    st.subheader("📦 عدّ البطاقات (أرقام 8 خانات) — بحث في القاعدة + الأرقام غير الموجودة")

    imgs_count = st.file_uploader(
        "📤 ارفع صور الصفحات (قد تحتوي أكثر من بطاقة)",
        type=["jpg","jpeg","png"],
        accept_multiple_files=True,
        key="ocr_count"
    )

    if imgs_count and st.button("🚀 عدّ البطاقات والبحث"):
        client = setup_google_vision()
        if client is None:
            st.error("❌ خطأ في إعداد Google Vision.")
        else:
            all_numbers, number_to_files, details = [], {}, []

            for img in imgs_count:
                try:
                    content = img.read()
                    image = vision.Image(content=content)
                    response = client.text_detection(image=image)
                    texts = response.text_annotations
                    full_text = texts[0].description if texts else ""

                    # استخراج أرقام مكونة من 8 خانات فقط
                    found_numbers = re.findall(r"\b\d{8}\b", full_text)
                    for n in found_numbers:
                        all_numbers.append(n)
                        number_to_files.setdefault(n, set()).add(img.name)

                    details.append({
                        "اسم الملف": img.name,
                        "عدد البطاقات (أرقام 8 خانات)": len(found_numbers),
                        "الأرقام المكتشفة (8 خانات فقط)": ", ".join(found_numbers) if found_numbers else "لا يوجد"
                    })

                except Exception as e:
                    st.warning(f"⚠️ خطأ أثناء معالجة صورة {img.name}: {e}")

            total_cards = len(all_numbers)
            unique_numbers = sorted(list(set(all_numbers)))

            st.success("✅ تم الاستخراج الأولي للأرقام")

            # ----------------- بحث في قاعدة البيانات عن الأرقام الموجودة -----------------
            found_df = pd.DataFrame()
            missing_list = []
            if unique_numbers:
                try:
                    conn = get_conn()
                    placeholders = ",".join(["%s"] * len(unique_numbers))
                    query = f"""
                        SELECT "رقم الناخب","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                               "اسم مركز الاقتراع","رقم مركز الاقتراع",
                               "المدينة","رقم مركز التسجيل","اسم مركز التسجيل","تاريخ الميلاد"
                        FROM "Bagdad" WHERE "رقم الناخب" IN ({placeholders})
                    """
                    found_df = pd.read_sql_query(query, conn, params=unique_numbers)
                    conn.close()

                    if not found_df.empty:
                        found_df = found_df.rename(columns={
                            "رقم الناخب": "رقم الناخب",
                            "الاسم الثلاثي": "الاسم",
                            "الجنس": "الجنس",
                            "هاتف": "رقم الهاتف",
                            "رقم العائلة": "رقم العائلة",
                            "اسم مركز الاقتراع": "مركز الاقتراع",
                            "رقم مركز الاقتراع": "رقم مركز الاقتراع",
                            "المدينة": "المدينة",
                            "رقم مركز التسجيل": "رقم مركز التسجيل",
                            "اسم مركز التسجيل": "اسم مركز التسجيل",
                            "تاريخ الميلاد": "تاريخ الميلاد"
                        })
                        found_df["الجنس"] = found_df["الجنس"].apply(map_gender)

                    found_numbers_in_db = set(found_df["رقم الناخب"].astype(str).tolist()) if not found_df.empty else set()
                    for n in unique_numbers:
                        if n not in found_numbers_in_db:
                            files = sorted(list(number_to_files.get(n, [])))
                            missing_list.append({"رقم_الناخب": n, "المصدر(الصور)": ", ".join(files)})
                except Exception as e:
                    st.error(f"❌ خطأ أثناء البحث في قاعدة البيانات: {e}")
            else:
                st.info("ℹ️ لم يتم العثور على أي أرقام مكوّنة من 8 خانات في الصور المرفوعة.")

            # ----------------- عرض النتائج للمستخدم -----------------
            st.markdown("### 📊 ملخص الاستخراج")
            st.metric("إجمالي الأرقام (مع التكرار)", total_cards)
            st.metric("إجمالي الأرقام الفريدة (8 خانات)", len(unique_numbers))
            st.metric("عدد الصور المرفوعة", len(imgs_count))

            st.markdown("### 🔎 بيانات الناخبين (الموجودة في قاعدة البيانات)")
            if not found_df.empty:
                st.dataframe(found_df, use_container_width=True, height=400)
                out_found = "found_voters.xlsx"
                found_df.to_excel(out_found, index=False, engine="openpyxl")
                with open(out_found, "rb") as f:
                    st.download_button("⬇️ تحميل بيانات الناخبين الموجودة", f,
                        file_name="بيانات_الناخبين_الموجودين.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.warning("⚠️ لم يتم العثور على أي مطابقات في قاعدة البيانات.")

            st.markdown("### ❌ الأرقام غير الموجودة في القاعدة (مع اسم الصورة)")
            if missing_list:
                missing_df = pd.DataFrame(missing_list)
                st.dataframe(missing_df, use_container_width=True)
                miss_file = "missing_numbers_with_files.xlsx"
                missing_df.to_excel(miss_file, index=False, engine="openpyxl")
                with open(miss_file, "rb") as f:
                    st.download_button("⬇️ تحميل الأرقام غير الموجودة مع المصدر", f,
                        file_name="الأرقام_غير_الموجودة_مع_المصدر.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.success("✅ لا توجد أرقام مفقودة (كل الأرقام الموجودة تم إيجادها في قاعدة البيانات).")

# ----------------------------------------------------------------------------- #
# 6) 🧾 التحقق من صحة المعلومات (بواسطة باسم)
# ----------------------------------------------------------------------------- #
with tab_check:
    st.subheader("🧾 التحقق من صحة بيانات الناخبين (بواسطة باسم ⚡ سريع)")

    st.markdown("""
    **📋 التعليمات:**
    - الملف يجب أن يحتوي الأعمدة التالية:
      1. رقم الناخب  
      2. الاسم  
      3. رقم العائلة  
      4. رقم مركز الاقتراع
    """)

    uploaded_check = st.file_uploader("📤 ارفع ملف Excel للتحقق", type=["xlsx"], key="check_file")

    if uploaded_check and st.button("🚀 بدء التحقق السريع بواسطة باسم"):
        try:
            df_check = pd.read_excel(uploaded_check, engine="openpyxl")

            required_cols = ["رقم الناخب", "الاسم", "رقم العائلة", "رقم مركز الاقتراع"]
            missing_cols = [c for c in required_cols if c not in df_check.columns]

            if missing_cols:
                st.error(f"❌ الملف ناقص الأعمدة التالية: {', '.join(missing_cols)}")
            else:
                # إظهار شريط التقدم باسم
                progress_bar = st.progress(0, text="🤖 باسم يحضّر البيانات...")
                total_steps = 4

                # الخطوة 1️⃣ - تحميل أرقام الناخبين من الملف
                voter_list = df_check["رقم الناخب"].astype(str).tolist()
                progress_bar.progress(1/total_steps, text="📥 تحميل أرقام الناخبين...")

                # الخطوة 2️⃣ - جلب كل البيانات من القاعدة دفعة واحدة
                conn = get_conn()
                placeholders = ",".join(["%s"] * len(voter_list))
                query = f"""
                    SELECT "رقم الناخب","الاسم الثلاثي","رقم العائلة","رقم مركز الاقتراع"
                    FROM "Bagdad"
                    WHERE "رقم الناخب" IN ({placeholders})
                """
                df_db = pd.read_sql_query(query, conn, params=voter_list)
                conn.close()
                progress_bar.progress(2/total_steps, text="💾 تم جلب البيانات من القاعدة...")

                # الخطوة 3️⃣ - دمج البيانات حسب رقم الناخب
                merged = pd.merge(
                    df_check.astype(str),
                    df_db.astype(str),
                    on="رقم الناخب",
                    how="left",
                    suffixes=("_المدخل", "_القاعدة")
                )

                progress_bar.progress(3/total_steps, text="🧠 باسم يقارن البيانات...")

                # الخطوة 4️⃣ - التحقق من التطابقات
                def match(a, b): return "✅" if a == b else "❌"

                merged["تطابق الاسم"] = merged.apply(lambda r: match(r["الاسم"], r["الاسم الثلاثي"]), axis=1)
                merged["تطابق رقم العائلة"] = merged.apply(lambda r: match(r["رقم العائلة_المدخل"], r["رقم العائلة_القاعدة"]), axis=1)
                merged["تطابق المركز"] = merged.apply(lambda r: match(r["رقم مركز الاقتراع_المدخل"], r["رقم مركز الاقتراع_القاعدة"]), axis=1)

                def overall(row):
                    if pd.isna(row["الاسم الثلاثي"]):
                        return "❌ غير موجود في القاعدة"
                    elif all(row[x] == "✅" for x in ["تطابق الاسم", "تطابق رقم العائلة", "تطابق المركز"]):
                        return "✅ مطابق"
                    else:
                        return "⚠️ اختلاف"

                merged["النتيجة النهائية"] = merged.apply(overall, axis=1)

                progress_bar.progress(1.0, text="✅ تم التحقق بواسطة باسم بسرعة ⚡")

                # عرض النتائج
                st.dataframe(merged[[
                    "رقم الناخب",
                    "الاسم",
                    "الاسم الثلاثي",
                    "تطابق الاسم",
                    "رقم العائلة_المدخل",
                    "رقم العائلة_القاعدة",
                    "تطابق رقم العائلة",
                    "رقم مركز الاقتراع_المدخل",
                    "رقم مركز الاقتراع_القاعدة",
                    "تطابق المركز",
                    "النتيجة النهائية"
                ]], use_container_width=True, height=450)

                # تحميل ملف النتائج
                out_file = "نتائج_التحقق_السريع.xlsx"
                merged.to_excel(out_file, index=False, engine="openpyxl")
                with open(out_file, "rb") as f:
                    st.download_button("⬇️ تحميل نتائج التحقق السريع", f,
                        file_name="نتائج_التحقق_السريع.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        except Exception as e:
            st.error(f"❌ خطأ أثناء التحقق: {e}")

# ----------------------------------------------------------------------------- #
# 8) 🧮 تحليل مخصص مع اختيار الأعمدة (Group & Count)
# ----------------------------------------------------------------------------- #
with tab_group:
    st.subheader("🧩 تحليل مخصص حسب الأعمدة المختارة")

    st.markdown("""
    **📋 التعليمات:**
    - ارفع ملف Excel يحتوي الأعمدة المطلوبة.  
    - اختر الأعمدة التي تريد تجميع النتائج بناءً عليها (مثلاً: *رقم مركز الاقتراع + رقم مركز التسجيل*).  
    - اختر العمود الذي تريد حساب عدد تكراراته (COUNT).  
    - باسم سيُظهر لك عدد الصفوف (الناخبين مثلًا) ضمن كل مجموعة 👇
    """)

    uploaded_group = st.file_uploader("📤 ارفع ملف Excel", type=["xlsx"], key="group_file")

    if uploaded_group:
        try:
            df = pd.read_excel(uploaded_group, engine="openpyxl")
            st.success(f"✅ تم تحميل الملف ({len(df)} صف)")

            st.markdown("### 🧱 الأعمدة المتوفرة:")
            st.write(list(df.columns))

            # اختيار الأعمدة للتجميع
            group_cols = st.multiselect("📊 اختر الأعمدة للتجميع (Group By):", options=df.columns)
            count_col = st.selectbox("🔢 اختر العمود المراد عده (COUNT):", options=df.columns)

            if group_cols and count_col and st.button("🚀 تنفيذ التحليل المخصص"):
                progress = st.progress(0, text="🤖 باسم يحلل البيانات...")
                total_steps = 3

                # الخطوة 1️⃣ - تجهيز البيانات
                progress.progress(1/total_steps, text="🧮 تجميع البيانات...")

                # الخطوة 2️⃣ - حساب عدد الصفوف حسب الأعمدة المحددة
                grouped = df.groupby(group_cols)[count_col].count().reset_index()
                grouped = grouped.rename(columns={count_col: "عدد الصفوف"})

                progress.progress(2/total_steps, text="📊 تجهيز النتائج...")

                # الخطوة 3️⃣ - عرض وتحميل النتائج
                st.dataframe(grouped, use_container_width=True, height=450)

                # زر تحميل النتائج
                out_file = "نتائج_تحليل_مخصص.xlsx"
                grouped.to_excel(out_file, index=False, engine="openpyxl")
                with open(out_file, "rb") as f:
                    st.download_button("⬇️ تحميل النتائج (Excel)", f,
                        file_name="نتائج_تحليل_مخصص.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                progress.progress(1.0, text="✅ تم التحليل بنجاح بواسطة باسم!")
        except Exception as e:
            st.error(f"❌ حدث خطأ أثناء التحليل: {e}")

