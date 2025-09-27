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
city = st.sidebar.selectbox("🏙️ اختر المدينة", ["Baghdad", "Babil"])
TABLE_NAME = "voters_data" if city == "Baghdad" else "Babil"

st.title(f"📊 المراقب الذكي - البحث في سجلات الناخبين ({city})")

# ====== التبويبات ======
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

    where_clauses, params = [], []
    if st.session_state.filters["voter"]:
        where_clauses.append('CAST(voter_no AS TEXT) ILIKE %s')
        params.append(f"%{st.session_state.filters['voter']}%")
    if st.session_state.filters["name"]:
        where_clauses.append('full_name ILIKE %s')
        params.append(f"%{st.session_state.filters['name']}%")
    if st.session_state.filters["center"]:
        where_clauses.append('polling_center_name ILIKE %s')
        params.append(f"%{st.session_state.filters['center']}%")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    count_sql = f'SELECT COUNT(*) FROM "{TABLE_NAME}" {where_sql};'
    offset = (st.session_state.page - 1) * page_size
    data_sql = f'''
        SELECT
            voter_no, full_name, gender, phone, family_number,
            polling_center_name, polling_center_number, station_number
        FROM "{TABLE_NAME}"
        {where_sql}
        ORDER BY voter_no ASC
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
                "voter_no": "رقم الناخب",
                "full_name": "الاسم",
                "gender": "الجنس",
                "phone": "رقم الهاتف",
                "family_number": "رقم العائلة",
                "polling_center_name": "مركز الاقتراع",
                "polling_center_number": "رقم مركز الاقتراع",
                "station_number": "رقم المحطة",
            })
            df["الجنس"] = df["الجنس"].apply(map_gender)

        total_pages = max(1, math.ceil(total_rows / page_size))

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
            query = f"""
                SELECT voter_no, full_name, gender, phone, family_number,
                       polling_center_name, polling_center_number, station_number
                FROM "{TABLE_NAME}" WHERE voter_no = %s
            """
            df = pd.read_sql_query(query, conn, params=(voter_input.strip(),))
            conn.close()

            if not df.empty:
                df = df.rename(columns={
                    "voter_no": "رقم الناخب",
                    "full_name": "الاسم",
                    "gender": "الجنس",
                    "phone": "رقم الهاتف",
                    "family_number": "رقم العائلة",
                    "polling_center_name": "مركز الاقتراع",
                    "polling_center_number": "رقم مركز الاقتراع",
                    "station_number": "رقم المحطة"
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
    uploaded_file = st.file_uploader("📤 ارفع ملف (voter_no)", type=["xlsx"])
    if uploaded_file and st.button("🚀 تشغيل البحث"):
        try:
            voters_df = pd.read_excel(uploaded_file, engine="openpyxl")
            voter_col = "voter_no" if "voter_no" in voters_df.columns else "رقم الناخب"
            voters_list = voters_df[voter_col].astype(str).tolist()

            conn = get_conn()
            placeholders = ",".join(["%s"] * len(voters_list))
            query = f"""
                SELECT voter_no, full_name, gender, phone, family_number,
                       polling_center_name, polling_center_number, station_number
                FROM "{TABLE_NAME}" WHERE voter_no IN ({placeholders})
            """
            df = pd.read_sql_query(query, conn, params=voters_list)
            conn.close()

            if not df.empty:
                df = df.rename(columns={
                    "voter_no": "رقم الناخب","full_name": "الاسم","gender": "الجنس",
                    "phone": "رقم الهاتف","family_number": "رقم العائلة",
                    "polling_center_name": "مركز الاقتراع","polling_center_number": "رقم مركز الاقتراع",
                    "station_number": "رقم المحطة"
                })
                df["الجنس"] = df["الجنس"].apply(map_gender)

                df["رقم المندوب الرئيسي"] = ""
                df["الحالة"] = 0
                df["ملاحظة"] = ""

                df = df[["رقم الناخب","الاسم","الجنس","رقم الهاتف",
                         "رقم العائلة","مركز الاقتراع","رقم مركز الاقتراع",
                         "رقم المحطة","رقم المندوب الرئيسي","الحالة","ملاحظة"]]

                found_numbers = set(df["رقم الناخب"].astype(str).tolist())
                missing_numbers = [num for num in voters_list if num not in found_numbers]

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

                if missing_numbers:
                    st.warning("⚠️ الأرقام التالية لم يتم العثور عليها:")
                    st.write(missing_numbers)
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
        if client is None:
            st.error("❌ خطأ في Google Vision.")
        else:
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

                        raw_candidates = re.findall(r"[0-9][0-9\-\s]{4,12}[0-9]", full_text)
                        for cand in raw_candidates:
                            if cand not in found_clear:
                                cleaned = re.sub(r"\D", "", cand)
                                if 6 <= len(cleaned) <= 10:
                                    unclear_candidates.append({"original": cand, "cleaned": cleaned})
                except Exception as e:
                    st.warning(f"⚠️ خطأ في {img.name}: {e}")

            clear_numbers = list(dict.fromkeys(clear_numbers))
            seen_cleaned, uniq_unclear = set(), []
            for item in unclear_candidates:
                if item["cleaned"] not in seen_cleaned and item["cleaned"] not in clear_numbers:
                    seen_cleaned.add(item["cleaned"])
                    uniq_unclear.append(item)

            if results:
                st.markdown("### 🖼️ الصور التي تحتوي أرقام ناخب:")
                for r in results:
                    st.image(r["content"], caption=f"{r['filename']} — {', '.join(r['numbers'])}", use_column_width=True)

            st.success("✅ تم الاستخراج")
            st.metric("الأرقام الواضحة", len(clear_numbers))
            st.metric("الأرقام المشكوك فيها", len(uniq_unclear))

            if clear_numbers:
                clear_df = pd.DataFrame(clear_numbers, columns=["الأرقام الواضحة"])
                clear_df.to_excel("clear_numbers.xlsx", index=False, engine="openpyxl")
                with open("clear_numbers.xlsx", "rb") as f:
                    st.download_button("⬇️ تحميل الأرقام الواضحة", f, file_name="الأرقام_الواضحة.xlsx")

            if uniq_unclear:
                unclear_df = pd.DataFrame(uniq_unclear)
                unclear_df.to_excel("unclear_numbers.xlsx", index=False, engine="openpyxl")
                with open("unclear_numbers.xlsx", "rb") as f:
                    st.download_button("⬇️ تحميل الأرقام المشكوك فيها", f, file_name="الأرقام_المشكوك_فيها.xlsx")

    st.markdown("---")

    # ---- استخراج + البحث ----
    imgs = st.file_uploader(
        "📤 ارفع صور للبحث المباشر",
        type=["jpg","jpeg","png"],
        accept_multiple_files=True,
        key="ocr_search"
    )
    if imgs and st.button("🚀 استخراج والبحث"):
        client = setup_google_vision()
        if client is None:
            st.error("❌ لم يتم تحميل مفتاح Google Vision.")
        else:
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

            if results:
                st.markdown("### 🖼️ الصور التي تحتوي أرقام:")
                for r in results:
                    st.image(r["content"], caption=f"{r['filename']} — {', '.join(r['numbers'])}", use_column_width=True)

            if all_voters:
                try:
                    conn = get_conn()
                    placeholders = ",".join(["%s"] * len(all_voters))
                    query = f"""
                        SELECT voter_no, full_name, gender, phone, family_number,
                               polling_center_name, polling_center_number, station_number
                        FROM "{TABLE_NAME}" WHERE voter_no IN ({placeholders})
                    """
                    df = pd.read_sql_query(query, conn, params=all_voters)
                    conn.close()

                    if not df.empty:
                        df = df.rename(columns={
                            "voter_no": "رقم الناخب","full_name": "الاسم","gender": "الجنس",
                            "phone": "رقم الهاتف","family_number": "رقم العائلة",
                            "polling_center_name": "مركز الاقتراع","polling_center_number": "رقم مركز الاقتراع",
                            "station_number": "رقم المحطة"
                        })
                        df["الجنس"] = df["الجنس"].apply(map_gender)

                        df["رقم المندوب الرئيسي"] = ""
                        df["الحالة"] = 0
                        df["ملاحظة"] = ""

                        st.dataframe(df, use_container_width=True, height=500)

                        df.to_excel("ocr_results.xlsx", index=False, engine="openpyxl")
                        with open("ocr_results.xlsx", "rb") as f:
                            st.download_button("⬇️ تحميل النتائج OCR", f, file_name="ocr_نتائج.xlsx")
                    else:
                        st.warning("⚠️ لم يتم العثور على نتائج")
                except Exception as e:
                    st.error(f"❌ خطأ أثناء البحث: {e}")
            else:
                st.warning("⚠️ لم يتم العثور على أرقام واضحة")

# ----------------------------------------------------------------------------- #
# 5) 📦 عدّ البطاقات (8 خانات) + الأرقام غير الموجودة
# ----------------------------------------------------------------------------- #
with tab_count:
    st.subheader("📦 عدّ البطاقات (8 خانات)")

    imgs_count = st.file_uploader(
        "📤 ارفع صور الصفحات",
        type=["jpg","jpeg","png"],
        accept_multiple_files=True,
        key="ocr_count"
    )
    if imgs_count and st.button("🚀 عدّ البطاقات والبحث"):
        client = setup_google_vision()
        if client is None:
            st.error("❌ خطأ في Google Vision.")
        else:
            all_numbers, number_to_files, details = [], {}, []

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

                    details.append({
                        "اسم الملف": img.name,
                        "عدد البطاقات": len(found_numbers),
                        "الأرقام": ", ".join(found_numbers) if found_numbers else "لا يوجد"
                    })
                except Exception as e:
                    st.warning(f"⚠️ خطأ في {img.name}: {e}")

            total_cards = len(all_numbers)
            unique_numbers = sorted(set(all_numbers))

            st.metric("إجمالي الأرقام", total_cards)
            st.metric("الأرقام الفريدة", len(unique_numbers))

            found_df, missing_list = pd.DataFrame(), []
            if unique_numbers:
                try:
                    conn = get_conn()
                    placeholders = ",".join(["%s"] * len(unique_numbers))
                    query = f"""
                        SELECT voter_no, full_name, gender, phone, family_number,
                               polling_center_name, polling_center_number, station_number
                        FROM "{TABLE_NAME}" WHERE voter_no IN ({placeholders})
                    """
                    found_df = pd.read_sql_query(query, conn, params=unique_numbers)
                    conn.close()

                    if not found_df.empty:
                        found_df = found_df.rename(columns={
                            "voter_no": "رقم الناخب","full_name": "الاسم","gender": "الجنس",
                            "phone": "رقم الهاتف","family_number": "رقم العائلة",
                            "polling_center_name": "مركز الاقتراع","polling_center_number": "رقم مركز الاقتراع",
                            "station_number": "رقم المحطة"
                        })
                        found_df["الجنس"] = found_df["الجنس"].apply(map_gender)

                    found_numbers_in_db = set(found_df["رقم الناخب"].astype(str).tolist()) if not found_df.empty else set()
                    for n in unique_numbers:
                        if n not in found_numbers_in_db:
                            files = sorted(list(number_to_files.get(n, [])))
                            missing_list.append({"رقم الناخب": n, "المصدر": ", ".join(files)})
                except Exception as e:
                    st.error(f"❌ خطأ أثناء البحث: {e}")

            st.markdown("### ✅ النتائج الموجودة")
            if not found_df.empty:
                st.dataframe(found_df, use_container_width=True, height=400)
                found_df.to_excel("found_voters.xlsx", index=False, engine="openpyxl")
                with open("found_voters.xlsx", "rb") as f:
                    st.download_button("⬇️ تحميل الموجودين", f, file_name="الموجودين.xlsx")
            else:
                st.warning("⚠️ لا يوجد نتائج")

            st.markdown("### ❌ الأرقام غير الموجودة")
            if missing_list:
                missing_df = pd.DataFrame(missing_list)
                st.dataframe(missing_df, use_container_width=True)
                missing_df.to_excel("missing_voters.xlsx", index=False, engine="openpyxl")
                with open("missing_voters.xlsx", "rb") as f:
                    st.download_button("⬇️ تحميل الغير موجودين", f, file_name="غير_موجودين.xlsx")
            else:
                st.success("✅ كل الأرقام موجودة")