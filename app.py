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

# ---- تحميل المتغيرات من .env ----
load_dotenv()

USERNAME = "admin"
PASSWORD = "Moraqip@123"

st.set_page_config(page_title="المراقب الذكي", layout="wide")

# ---- إعداد Google Vision ----
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
        return "أنثى" if val == 1 else "ذكر"
    except:
        return "ذكر"

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

# ====== التبويبات ======
tab_search, tab_single, tab_file, tab_ocr, tab_count = st.tabs(
    ["🏫 بحث بالمراكز والفلاتر", "🔍 بحث برقم", "📂 رفع ملف Excel", "📸 OCR صور بطاقات", "📦 عدّ البطاقات"]
)

# ----------------------------------------------------------------------------- #
# 1) 🏫 بحث بالمراكز والفلاتر (بديل تصفّح السجلات)
# ----------------------------------------------------------------------------- #
with tab_search:
    st.subheader("🏫 البحث باستخدام المراكز + الفلاتر")

    try:
        conn = get_conn()
        # تحميل أسماء المراكز بشكل منفصل لتسهيل البحث
        centers_df = pd.read_sql('SELECT DISTINCT "اسم مركز الاقتراع","رقم مركز الاقتراع" FROM voters ORDER BY "اسم مركز الاقتراع";', conn)
        reg_df = pd.read_sql('SELECT DISTINCT "اسم مركز التسجيل","رقم مركز التسجيل" FROM voters ORDER BY "اسم مركز التسجيل";', conn)
        conn.close()
    except Exception as e:
        st.error(f"❌ خطأ أثناء تحميل المراكز: {e}")
        centers_df, reg_df = pd.DataFrame(), pd.DataFrame()

    col1, col2 = st.columns(2)
    with col1:
        center_name = st.selectbox("🏫 اختر اسم مركز الاقتراع", [""] + centers_df["اسم مركز الاقتراع"].tolist(), index=0)
        center_no = st.selectbox("🔢 اختر رقم مركز الاقتراع", [""] + centers_df["رقم مركز الاقتراع"].astype(str).tolist(), index=0)
    with col2:
        reg_name = st.selectbox("📌 اختر اسم مركز التسجيل", [""] + reg_df["اسم مركز التسجيل"].tolist(), index=0)
        reg_no = st.selectbox("🔢 اختر رقم مركز التسجيل", [""] + reg_df["رقم مركز التسجيل"].astype(str).tolist(), index=0)

    # فلاتر إضافية
    colf1, colf2, colf3 = st.columns(3)
    with colf1:
        phone_filter = st.text_input("📱 رقم الهاتف:")
    with colf2:
        family_filter = st.text_input("👨‍👩‍👦 رقم العائلة:")
    with colf3:
        gender_filter = st.selectbox("⚧ الجنس:", ["", "ذكر", "أنثى"], index=0)

    page_size = st.selectbox("عدد الصفوف", [10, 20, 50, 100], index=1)

    if st.button("🔎 تنفيذ البحث"):
        where_clauses, params = [], []

        if center_name:
            where_clauses.append('"اسم مركز الاقتراع" = %s')
            params.append(center_name)
        if center_no:
            where_clauses.append('"رقم مركز الاقتراع" = %s')
            params.append(center_no)
        if reg_name:
            where_clauses.append('"اسم مركز التسجيل" = %s')
            params.append(reg_name)
        if reg_no:
            where_clauses.append('"رقم مركز التسجيل" = %s')
            params.append(reg_no)
        if phone_filter:
            where_clauses.append('"هاتف" ILIKE %s')
            params.append(f"%{phone_filter}%")
        if family_filter:
            where_clauses.append('"رقم العائلة" ILIKE %s')
            params.append(f"%{family_filter}%")
        if gender_filter:
            if gender_filter == "أنثى":
                where_clauses.append('"الجنس" = 1')
            elif gender_filter == "ذكر":
                where_clauses.append('"الجنس" = 0')

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
            SELECT "VoterNo","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                   "اسم مركز التسجيل","رقم مركز التسجيل",
                   "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
            FROM voters
            {where_sql}
            ORDER BY "VoterNo" ASC
            LIMIT %s;
        """
        params.append(page_size)

        try:
            conn = get_conn()
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()

            if not df.empty:
                df = df.rename(columns={
                    "VoterNo": "رقم الناخب",
                    "الاسم الثلاثي": "الاسم",
                    "الجنس": "الجنس",
                    "هاتف": "رقم الهاتف",
                    "رقم العائلة": "رقم العائلة",
                    "اسم مركز التسجيل": "مركز التسجيل",
                    "رقم مركز التسجيل": "رقم مركز التسجيل",
                    "اسم مركز الاقتراع": "مركز الاقتراع",
                    "رقم مركز الاقتراع": "رقم مركز الاقتراع",
                    "رقم المحطة": "رقم المحطة"
                })
                df["الجنس"] = df["الجنس"].apply(map_gender)

                st.dataframe(df, use_container_width=True, height=500)
            else:
                st.warning("⚠️ لا توجد نتائج حسب الفلاتر المحددة")
        except Exception as e:
            st.error(f"❌ خطأ أثناء البحث: {e}")
# ----------------------------------------------------------------------------- #
# 2) 🔍 البحث برقم واحد
# ----------------------------------------------------------------------------- #
with tab_single:
    st.subheader("🔍 البحث برقم الناخب أو رقم العائلة")

    col1, col2 = st.columns(2)
    with col1:
        voter_input = st.text_input("ادخل رقم الناخب:")
    with col2:
        family_input = st.text_input("ادخل رقم العائلة:")

    if st.button("بحث"):
        try:
            where_clauses, params = [], []
            if voter_input.strip():
                where_clauses.append('"VoterNo" = %s')
                params.append(voter_input.strip())
            if family_input.strip():
                where_clauses.append('"رقم العائلة" = %s')
                params.append(family_input.strip())

            where_sql = f"WHERE {' OR '.join(where_clauses)}" if where_clauses else ""

            query = f"""
                SELECT "VoterNo","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                       "اسم مركز التسجيل","رقم مركز التسجيل",
                       "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
                FROM voters
                {where_sql}
            """

            conn = get_conn()
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()

            if not df.empty:
                df = df.rename(columns={
                    "VoterNo": "رقم الناخب",
                    "الاسم الثلاثي": "الاسم",
                    "الجنس": "الجنس",
                    "هاتف": "رقم الهاتف",
                    "رقم العائلة": "رقم العائلة",
                    "اسم مركز التسجيل": "مركز التسجيل",
                    "رقم مركز التسجيل": "رقم مركز التسجيل",
                    "اسم مركز الاقتراع": "مركز الاقتراع",
                    "رقم مركز الاقتراع": "رقم مركز الاقتراع",
                    "رقم المحطة": "رقم المحطة"
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

    uploaded_file = st.file_uploader("📤 ارفع ملف (VoterNo أو رقم الناخب)", type=["xlsx"])
    if uploaded_file and st.button("🚀 تشغيل البحث"):
        try:
            voters_df = pd.read_excel(uploaded_file, engine="openpyxl")

            # ✅ دعم العمود بالعربي أو بالإنجليزي
            voter_col = "VoterNo" if "VoterNo" in voters_df.columns else "رقم الناخب"
            voters_list = voters_df[voter_col].astype(str).tolist()

            conn = get_conn()
            placeholders = ",".join(["%s"] * len(voters_list))
            query = f"""
                SELECT "VoterNo","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                       "اسم مركز التسجيل","رقم مركز التسجيل",
                       "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
                FROM voters WHERE "VoterNo" IN ({placeholders})
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
                    "اسم مركز التسجيل": "مركز التسجيل",
                    "رقم مركز التسجيل": "رقم مركز التسجيل",
                    "اسم مركز الاقتراع": "مركز الاقتراع",
                    "رقم مركز الاقتراع": "رقم مركز الاقتراع",
                    "رقم المحطة": "رقم المحطة"
                })
                df["الجنس"] = df["الجنس"].apply(map_gender)

                # ✅ إضافة أعمدة إضافية (قابلة للتعديل لاحقًا)
                df["رقم المندوب الرئيسي"] = ""
                df["الحالة"] = 0
                df["ملاحظة"] = ""

                # ترتيب الأعمدة
                df = df[[
                    "رقم الناخب","الاسم","الجنس","رقم الهاتف",
                    "رقم العائلة","مركز التسجيل","رقم مركز التسجيل",
                    "مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة",
                    "رقم المندوب الرئيسي","الحالة","ملاحظة"
                ]]

                # ✅ إيجاد الأرقام غير الموجودة
                found_numbers = set(df["رقم الناخب"].astype(str).tolist())
                missing_numbers = [num for num in voters_list if num not in found_numbers]

                # عرض النتائج
                st.dataframe(df, use_container_width=True, height=500)

                # ملف النتائج
                output_file = "نتائج_البحث.xlsx"
                df.to_excel(output_file, index=False, engine="openpyxl")
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

    # ---- قسم: استخراج الأرقام فقط (بدون البحث) ----
    st.markdown("### 🔎 استخراج الأرقام فقط (بدون البحث في قاعدة البيانات)")
    imgs_only = st.file_uploader(
        "📤 ارفع صور البطاقات (لاستخراج الأرقام فقط)",
        type=["jpg","jpeg","png"],
        accept_multiple_files=True,
        key="ocr_only"
    )
    if imgs_only and st.button("🚀 استخراج الأرقام فقط"):
        client = setup_google_vision()
        if client is None:
            st.error("❌ خطأ في إعداد Google Vision.")
        else:
            clear_numbers = []
            unclear_candidates = []
            results = []

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

                        raw_candidates = re.findall(r"[0-9][0-9\-\s]{4,12}[0-9]", full_text)
                        for cand in raw_candidates:
                            if cand not in found_clear:
                                cleaned = re.sub(r"\D", "", cand)
                                if 6 <= len(cleaned) <= 10:
                                    unclear_candidates.append({"original": cand, "cleaned": cleaned})
                except Exception as e:
                    st.warning(f"⚠️ خطأ أثناء معالجة صورة: {e}")

            # إزالة التكرارات
            clear_numbers = list(dict.fromkeys(clear_numbers))
            seen_cleaned = set()
            uniq_unclear = []
            for item in unclear_candidates:
                if item["cleaned"] not in seen_cleaned and item["cleaned"] not in clear_numbers:
                    seen_cleaned.add(item["cleaned"])
                    uniq_unclear.append(item)

            # ✅ عرض الصور التي فيها أرقام
            if results:
                st.markdown("### 🖼️ الصور التي تحتوي أرقام ناخب (مرفقة ✅):")
                for r in results:
                    numbers_str = ", ".join(r["numbers"])
                    st.image(r["content"], caption=f"{r['filename']} — الأرقام: {numbers_str}", use_column_width=True)

            st.success("✅ الانتهاء من الاستخراج")
            st.metric("الأرقام الواضحة المكتشفة", len(clear_numbers))
            st.metric("الأرقام المشكوك فيها (غير واضحة)", len(uniq_unclear))

            # ✅ تحميل الملفات
            if clear_numbers:
                clear_df = pd.DataFrame(clear_numbers, columns=["الأرقام الواضحة"])
                clear_file = "clear_numbers.xlsx"
                clear_df.to_excel(clear_file, index=False, engine="openpyxl")
                with open(clear_file, "rb") as f:
                    st.download_button("⬇️ تحميل الأرقام الواضحة", f,
                        file_name="الأرقام_الواضحة.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            if uniq_unclear:
                unclear_df = pd.DataFrame(uniq_unclear)
                unclear_file = "unclear_numbers.xlsx"
                unclear_df.to_excel(unclear_file, index=False, engine="openpyxl")
                with open(unclear_file, "rb") as f:
                    st.download_button("⬇️ تحميل الأرقام المشكوك فيها", f,
                        file_name="الأرقام_المشكوك_فيها.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.markdown("---")

    # ---- قسم: استخراج + البحث في قاعدة البيانات ----
    imgs = st.file_uploader(
        "📤 ارفع صور البطاقات (للاستخراج والبحث في قاعدة البيانات)",
        type=["jpg","jpeg","png"],
        accept_multiple_files=True,
        key="ocr_search"
    )
    if imgs and st.button("🚀 استخراج والبحث"):
        client = setup_google_vision()
        if client is None:
            st.error("❌ لم يتم تحميل مفتاح Google Vision بشكل صحيح.")
        else:
            all_voters = []
            results = []

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
                    st.warning(f"⚠️ خطأ أثناء معالجة صورة: {e}")

            # ✅ عرض الصور
            if results:
                st.markdown("### 🖼️ الصور التي تحتوي أرقام ناخب:")
                for r in results:
                    st.image(r["content"], caption=f"{r['filename']} — الأرقام: {', '.join(r['numbers'])}", use_column_width=True)

            # ✅ البحث في قاعدة البيانات
            if all_voters:
                try:
                    conn = get_conn()
                    placeholders = ",".join(["%s"] * len(all_voters))
                    query = f"""
                        SELECT "VoterNo","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                               "اسم مركز التسجيل","رقم مركز التسجيل",
                               "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
                        FROM voters WHERE "VoterNo" IN ({placeholders})
                    """
                    df = pd.read_sql_query(query, conn, params=all_voters)
                    conn.close()

                    if not df.empty:
                        df = df.rename(columns={
                            "VoterNo": "رقم الناخب","الاسم الثلاثي": "الاسم","الجنس": "الجنس",
                            "هاتف": "رقم الهاتف","رقم العائلة": "رقم العائلة",
                            "اسم مركز التسجيل": "مركز التسجيل","رقم مركز التسجيل": "رقم مركز التسجيل",
                            "اسم مركز الاقتراع": "مركز الاقتراع","رقم مركز الاقتراع": "رقم مركز الاقتراع",
                            "رقم المحطة": "رقم المحطة"
                        })
                        df["الجنس"] = df["الجنس"].apply(map_gender)

                        df["رقم المندوب الرئيسي"] = ""
                        df["الحالة"] = 0
                        df["ملاحظة"] = ""

                        st.dataframe(df, use_container_width=True, height=500)

                        output_file = "ocr_نتائج_البحث.xlsx"
                        df.to_excel(output_file, index=False, engine="openpyxl")
                        with open(output_file, "rb") as f:
                            st.download_button("⬇️ تحميل النتائج OCR", f,
                                file_name="ocr_نتائج_البحث.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    else:
                        st.warning("⚠️ لم يتم العثور على نتائج")
                except Exception as e:
                    st.error(f"❌ خطأ أثناء البحث في قاعدة البيانات: {e}")
            else:
                st.warning("⚠️ لم يتعرّف على أي أرقام في الصور")
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
            all_numbers = []               # جميع الأرقام المكتشفة (مع التكرار)
            number_to_files = {}           # خريطة: رقم -> أسماء الصور
            details = []                   # تفاصيل لكل صورة

            # 🔎 استخراج الأرقام من الصور
            for img in imgs_count:
                try:
                    content = img.read()
                    image = vision.Image(content=content)
                    response = client.text_detection(image=image)
                    texts = response.text_annotations
                    full_text = texts[0].description if texts else ""

                    # استخراج فقط الأرقام المكونة من 8 خانات
                    found_numbers = re.findall(r"\b\d{8}\b", full_text)
                    for n in found_numbers:
                        all_numbers.append(n)
                        number_to_files.setdefault(n, set()).add(img.name)

                    details.append({
                        "اسم الملف": img.name,
                        "عدد البطاقات (8 خانات)": len(found_numbers),
                        "الأرقام المكتشفة": ", ".join(found_numbers) if found_numbers else "لا يوجد"
                    })

                except Exception as e:
                    st.warning(f"⚠️ خطأ أثناء معالجة صورة {img.name}: {e}")

            total_cards = len(all_numbers)
            unique_numbers = sorted(list(set(all_numbers)))

            st.success("✅ تم استخراج الأرقام الأولية")

            # ----------------- 🔍 البحث في قاعدة البيانات -----------------
            found_df = pd.DataFrame()
            missing_list = []
            if unique_numbers:
                try:
                    conn = get_conn()
                    placeholders = ",".join(["%s"] * len(unique_numbers))
                    query = f"""
                        SELECT "VoterNo","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                               "اسم مركز التسجيل","رقم مركز التسجيل",
                               "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
                        FROM voters WHERE "VoterNo" IN ({placeholders})
                    """
                    found_df = pd.read_sql_query(query, conn, params=unique_numbers)
                    conn.close()

                    if not found_df.empty:
                        found_df = found_df.rename(columns={
                            "VoterNo": "رقم الناخب",
                            "الاسم الثلاثي": "الاسم",
                            "الجنس": "الجنس",
                            "هاتف": "رقم الهاتف",
                            "رقم العائلة": "رقم العائلة",
                            "اسم مركز التسجيل": "مركز التسجيل",
                            "رقم مركز التسجيل": "رقم مركز التسجيل",
                            "اسم مركز الاقتراع": "مركز الاقتراع",
                            "رقم مركز الاقتراع": "رقم مركز الاقتراع",
                            "رقم المحطة": "رقم المحطة"
                        })
                        found_df["الجنس"] = found_df["الجنس"].apply(map_gender)

                    # استخراج الأرقام غير الموجودة
                    found_numbers_in_db = set(found_df["رقم الناخب"].astype(str).tolist()) if not found_df.empty else set()
                    for n in unique_numbers:
                        if n not in found_numbers_in_db:
                            files = sorted(list(number_to_files.get(n, [])))
                            missing_list.append({"رقم_الناخب": n, "المصدر (الصور)": ", ".join(files)})

                except Exception as e:
                    st.error(f"❌ خطأ أثناء البحث في قاعدة البيانات: {e}")
            else:
                st.info("ℹ️ لم يتم العثور على أي أرقام مكونة من 8 خانات.")

            # ----------------- 📊 عرض الملخص -----------------
            st.markdown("### 📊 ملخص النتائج")
            st.metric("إجمالي الأرقام (مع التكرار)", total_cards)
            st.metric("إجمالي الأرقام الفريدة", len(unique_numbers))
            st.metric("عدد الصور المرفوعة", len(imgs_count))

            # ✅ بيانات الناخبين الموجودة
            st.markdown("### ✅ بيانات الناخبين الموجودة في القاعدة")
            if not found_df.empty:
                st.dataframe(found_df, use_container_width=True, height=400)
                out_found = "found_voters.xlsx"
                found_df.to_excel(out_found, index=False, engine="openpyxl")
                with open(out_found, "rb") as f:
                    st.download_button("⬇️ تحميل النتائج الموجودة", f,
                        file_name="بيانات_الناخبين.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.warning("⚠️ لم يتم العثور على أي مطابقات")

            # ❌ الأرقام غير الموجودة
            st.markdown("### ❌ الأرقام غير الموجودة")
            if missing_list:
                missing_df = pd.DataFrame(missing_list)
                st.dataframe(missing_df, use_container_width=True)
                miss_file = "missing_numbers.xlsx"
                missing_df.to_excel(miss_file, index=False, engine="openpyxl")
                with open(miss_file, "rb") as f:
                    st.download_button("⬇️ تحميل الأرقام غير الموجودة", f,
                        file_name="الأرقام_غير_الموجودة.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.success("✅ جميع الأرقام موجودة في قاعدة البيانات")
