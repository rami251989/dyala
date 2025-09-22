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

# ====== تبويبات ======
tab_browse, tab_single, tab_file, tab_ocr, tab_count = st.tabs(
    ["📄 تصفّح السجلات", "🔍 بحث برقم", "📂 رفع ملف Excel", "📸 OCR صور بطاقات", "📦 عدّ البطاقات"]
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
            "VoterNo","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
            "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
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
                SELECT "VoterNo","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                       "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
                FROM voters WHERE "VoterNo" = %s
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
                    "رقم المحطة": "رقم محطة"
                })
                df["الجنس"] = df["الجنس"].apply(map_gender)

                st.dataframe(df, use_container_width=True, height=500)
            else:
                st.warning("⚠️ لم يتم العثور على نتائج")
        except Exception as e:
            st.error(f"❌ خطأ: {e}")

# ----------------------------------------------------------------------------- #
# 3) 📂 رفع ملف Excel
# ----------------------------------------------------------------------------- #
with tab_file:
    st.subheader("📂 البحث باستخدام ملف Excel")
    uploaded_file = st.file_uploader("📤 ارفع ملف (VoterNo)", type=["xlsx"])
    if uploaded_file and st.button("🚀 تشغيل البحث"):
        try:
            voters_df = pd.read_excel(uploaded_file, engine="openpyxl")
            voter_col = "VoterNo" if "VoterNo" in voters_df.columns else "رقم الناخب"
            voters_list = voters_df[voter_col].astype(str).tolist()

            conn = get_conn()
            placeholders = ",".join(["%s"] * len(voters_list))
            query = f"""
                SELECT "VoterNo","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                       "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
                FROM voters WHERE "VoterNo" IN ({placeholders})
            """
            df = pd.read_sql_query(query, conn, params=voters_list)
            conn.close()

            if not df.empty:
                df = df.rename(columns={
                    "VoterNo": "رقم الناخب","الاسم الثلاثي": "الاسم","الجنس": "الجنس",
                    "هاتف": "رقم الهاتف","رقم العائلة": "رقم العائلة",
                    "اسم مركز الاقتراع": "مركز الاقتراع","رقم مركز الاقتراع": "رقم مركز الاقتراع",
                    "رقم المحطة": "رقم المحطة"
                })
                df["الجنس"] = df["الجنس"].apply(map_gender)

                df["رقم المندوب الرئيسي"] = ""
                df["الحالة"] = 0
                df["ملاحظة"] = ""

                df = df[["رقم الناخب","الاسم","الجنس","رقم الهاتف",
                         "رقم العائلة","مركز الاقتراع","رقم مركز الاقتراع",
                         "رقم المحطة","رقم المندوب الرئيسي","الحالة","ملاحظة"]]

                st.dataframe(df, use_container_width=True, height=500)

                output_file = "نتائج_البحث.xlsx"
                df.to_excel(output_file, index=False, engine="openpyxl")
                wb = load_workbook(output_file)
                wb.active.sheet_view.rightToLeft = True
                wb.save(output_file)
                with open(output_file, "rb") as f:
                    st.download_button("⬇️ تحميل النتائج", f,
                        file_name="نتائج_البحث.xlsx",
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

                        # فقط نحتفظ بالصور التي تحتوي أرقام ناخب واضحة
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

            clear_numbers = list(dict.fromkeys(clear_numbers))
            seen_cleaned = set()
            uniq_unclear = []
            for item in unclear_candidates:
                if item["cleaned"] not in seen_cleaned and item["cleaned"] not in clear_numbers:
                    seen_cleaned.add(item["cleaned"])
                    uniq_unclear.append(item)

            if results:
                st.markdown("### 🖼️ الصور التي تحتوي أرقام ناخب (مرفقة ✅):")
                for r in results:
                    numbers_str = ", ".join(r["numbers"])
                    st.image(r["content"], caption=f"{r['filename']} — الأرقام: {numbers_str}", use_column_width=True)

            st.success("✅ الانتهاء من الاستخراج")
            st.metric("الأرقام الواضحة المكتشفة", len(clear_numbers))
            st.metric("الأرقام المشكوك فيها (غير واضحة)", len(uniq_unclear))

            if clear_numbers:
                st.markdown("**قائمة الأرقام الواضحة:**")
                st.write(clear_numbers)
                clear_df = pd.DataFrame(clear_numbers, columns=["الأرقام الواضحة"])
                clear_file = "clear_numbers.xlsx"
                clear_df.to_excel(clear_file, index=False, engine="openpyxl")
                with open(clear_file, "rb") as f:
                    st.download_button("⬇️ تحميل الأرقام الواضحة", f,
                        file_name="الأرقام_الواضحة.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            if uniq_unclear:
                st.markdown("**قائمة الأرقام غير الواضحة (الأصلية → بعد التنظيف):**")
                st.dataframe(uniq_unclear)
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
            results = []  # صور التي تحتوي أرقام

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

            if results:
                st.markdown("### 🖼️ الصور التي تحتوي أرقام ناخب:")
                for r in results:
                    st.image(r["content"], caption=f"{r['filename']} — الأرقام: {', '.join(r['numbers'])}", use_column_width=True)

            if all_voters:
                try:
                    conn = get_conn()
                    placeholders = ",".join(["%s"] * len(all_voters))
                    query = f"""
                        SELECT "VoterNo","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                               "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
                        FROM voters WHERE "VoterNo" IN ({placeholders})
                    """
                    df = pd.read_sql_query(query, conn, params=all_voters)
                    conn.close()

                    if not df.empty:
                        df = df.rename(columns={
                            "VoterNo": "رقم الناخب","الاسم الثلاثي": "الاسم","الجنس": "الجنس",
                            "هاتف": "رقم الهاتف","رقم العائلة": "رقم العائلة",
                            "اسم مركز الاقتراع": "مركز الاقتراع","رقم مركز الاقتراع": "رقم مركز الاقتراع",
                            "رقم المحطة": "رقم المحطة"
                        })
                        df["الجنس"] = df["الجنس"].apply(map_gender)

                        df["رقم المندوب الرئيسي"] = ""
                        df["الحالة"] = 0
                        df["ملاحظة"] = ""

                        df = df[["رقم الناخب","الاسم","الجنس","رقم الهاتف",
                                 "رقم العائلة","مركز الاقتراع","رقم مركز الاقتراع",
                                 "رقم المحطة","رقم المندوب الرئيسي","الحالة","ملاحظة"]]

                        st.dataframe(df, use_container_width=True, height=500)

                        output_file = "ocr_نتائج_البحث.xlsx"
                        df.to_excel(output_file, index=False, engine="openpyxl")
                        wb = load_workbook(output_file)
                        wb.active.sheet_view.rightToLeft = True
                        wb.save(output_file)
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
# 5) 📦 عدّ البطاقات
# ----------------------------------------------------------------------------- #
with tab_count:
    st.subheader("📦 عدّ البطاقات (عدد البطاقات = عدد أرقام الناخب داخل الصور)")

    imgs_count = st.file_uploader(
        "📤 ارفع صور الصفحات (قد تحتوي أكثر من بطاقة)",
        type=["jpg","jpeg","png"],
        accept_multiple_files=True,
        key="ocr_count"
    )

    if imgs_count and st.button("🚀 عدّ البطاقات"):
        client = setup_google_vision()
        if client is None:
            st.error("❌ خطأ في إعداد Google Vision.")
        else:
            all_numbers = []   # كل الأرقام من جميع الصور
            details = []       # تفاصيل لكل صورة

            for img in imgs_count:
                try:
                    content = img.read()
                    image = vision.Image(content=content)
                    response = client.text_detection(image=image)
                    texts = response.text_annotations
                    if texts:
                        found_numbers = re.findall(r"\b\d{6,10}\b", texts[0].description)
                        all_numbers.extend(found_numbers)

                        details.append({
                            "اسم الملف": img.name,
                            "عدد البطاقات": len(found_numbers),
                            "الأرقام المكتشفة": ", ".join(found_numbers) if found_numbers else "لا يوجد"
                        })
                except Exception as e:
                    st.warning(f"⚠️ خطأ أثناء معالجة صورة: {e}")

            total_cards = len(all_numbers)

            # ✅ عرض النتائج
            st.success("✅ تم الانتهاء من العدّ")
            st.metric("إجمالي عدد البطاقات المكتشفة", total_cards)
            st.metric("عدد الصور المرفوعة", len(imgs_count))

            if details:
                st.markdown("### 📋 تفاصيل كل صورة:")
                df = pd.DataFrame(details)
                st.dataframe(df, use_container_width=True)

                # تحميل النتائج Excel
                out_file = "إحصائية_البطاقات.xlsx"
                df.to_excel(out_file, index=False, engine="openpyxl")
                with open(out_file, "rb") as f:
                    st.download_button("⬇️ تحميل ملف الإحصائية", f,
                        file_name="إحصائية_البطاقات.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
