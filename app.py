# =========================
# الجزء 1: الإعدادات والدوال
# =========================
import os
import math
import re
import base64
import pandas as pd
import streamlit as st
import psycopg2
from openpyxl import load_workbook
from dotenv import load_dotenv
from google.cloud import vision

# ---- الإعدادات العامة / البيئة ----
load_dotenv()
st.set_page_config(page_title="المراقب الذكي", layout="wide")

USERNAME = "admin"
PASSWORD = "Moraqip@123"

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

# ---- تحويل الجنس (0 ذكر / 1 أنثى) إلى نص عربي ----
def map_gender(x):
    try:
        v = int(float(x))
        return "أنثى" if v == 1 else "ذكر"
    except:
        return "ذكر"

# ---- تنسيق النتائج إلى الستركشر المطلوب ----
# رقم الناخب | الاسم | الجنس | رقم الهاتف | رقم العائلة | مركز الاقتراع | رقم مركز الاقتراع | رقم المحطة | رقم المندوب الرئيسي | الحالة | ملاحظة
def format_results(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    # إعادة تسمية الأعمدة القادمة من قاعدة البيانات إلى العربية الموحدة
    rename_map = {
        "VoterNo": "رقم الناخب",
        "الاسم الثلاثي": "الاسم",
        "الجنس": "الجنس",
        "هاتف": "رقم الهاتف",
        "رقم العائلة": "رقم العائلة",
        "اسم مركز الاقتراع": "مركز الاقتراع",
        "رقم مركز الاقتراع": "رقم مركز الاقتراع",
        "رقم المحطة": "رقم المحطة",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # تحويل الجنس إلى نص عربي
    if "الجنس" in df.columns:
        df["الجنس"] = df["الجنس"].apply(map_gender)

    # إضافة الأعمدة المطلوبة إن لم تكن موجودة
    for col, default_val in [
        ("رقم المندوب الرئيسي", ""),
        ("الحالة", 0),
        ("ملاحظة", ""),
    ]:
        if col not in df.columns:
            df[col] = default_val

    # ترتيب الأعمدة بالضبط كما طلبت
    ordered_cols = [
        "رقم الناخب", "الاسم", "الجنس", "رقم الهاتف",
        "رقم العائلة", "مركز الاقتراع", "رقم مركز الاقتراع",
        "رقم المحطة", "رقم المندوب الرئيسي", "الحالة", "ملاحظة"
    ]
    # أي عمود ناقص (من الأساسية) نضيفه فارغ
    for c in ordered_cols:
        if c not in df.columns:
            df[c] = "" if c not in ("الحالة",) else 0

    df = df[ordered_cols]
    return df

# ---- تسجيل الدخول ----
def login():
    st.markdown("## 🔑 تسجيل الدخول")
    u = st.text_input("👤 اسم المستخدم")
    p = st.text_input("🔒 كلمة المرور", type="password")
    if st.button("دخول"):
        if u == USERNAME and p == PASSWORD:
            st.session_state.logged_in = True
            st.success("✅ تم تسجيل الدخول")
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

# ====== اختيار المدينة (فلتر أساسي) ======
city = st.selectbox("🏙️ اختر المدينة:", ["Bagdad", "Babil"])
table_name = f'"{city}"'   # عشان نستخدمها في الاستعلامات

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
        st.session_state.filters = {
            "voter": "",
            "name": "",
            "center": "",
            "family": "",
            "phone": "",
            "gender": ""
        }

    # ---- واجهة الفلاتر ----
    colf1, colf2, colf3 = st.columns([1,1,1])
    with colf1:
        voter_filter = st.text_input("🔢 رقم الناخب:", value=st.session_state.filters["voter"])
        family_filter = st.text_input("👨‍👩‍👦 رقم العائلة:", value=st.session_state.filters["family"])
    with colf2:
        name_filter = st.text_input("🧑‍💼 الاسم:", value=st.session_state.filters["name"])
        phone_filter = st.text_input("📞 رقم الهاتف:", value=st.session_state.filters["phone"])
    with colf3:
        center_filter = st.text_input("🏫 مركز الاقتراع:", value=st.session_state.filters["center"])
        gender_filter = st.selectbox("⚧ الجنس:", ["", "ذكر", "أنثى"])

    page_size = st.selectbox("عدد الصفوف", [10, 20, 50, 100], index=1)

    if st.button("🔎 تطبيق الفلاتر"):
        st.session_state.filters = {
            "voter": voter_filter.strip(),
            "name": name_filter.strip(),
            "center": center_filter.strip(),
            "family": family_filter.strip(),
            "phone": phone_filter.strip(),
            "gender": gender_filter.strip()
        }
        st.session_state.page = 1

    # --- بناء شروط البحث ---
    where_clauses, params = [], []
    f = st.session_state.filters

    if f["voter"]:
        where_clauses.append('CAST("رقم الناخب" AS TEXT) ILIKE %s')
        params.append(f"%{f['voter']}%")
    if f["name"]:
        where_clauses.append('"الاسم الثلاثي" ILIKE %s')
        params.append(f"%{f['name']}%")
    if f["center"]:
        where_clauses.append('"اسم مركز الاقتراع" ILIKE %s')
        params.append(f"%{f['center']}%")
    if f["family"]:
        where_clauses.append('CAST("رقم العائلة" AS TEXT) ILIKE %s')
        params.append(f"%{f['family']}%")
    if f["phone"]:
        where_clauses.append('CAST("هاتف" AS TEXT) ILIKE %s')
        params.append(f"%{f['phone']}%")
    if f["gender"] == "ذكر":
        where_clauses.append('"الجنس" = 0')
    elif f["gender"] == "أنثى":
        where_clauses.append('"الجنس" = 1')

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # --- SQL ---
    count_sql = f'SELECT COUNT(*) FROM {table_name} {where_sql};'
    offset = (st.session_state.page - 1) * page_size
    data_sql = f'''
        SELECT
            "رقم الناخب","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
            "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
        FROM {table_name}
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
                "رقم المحطة": "رقم المحطة",
            })
            df["الجنس"] = df["الجنس"].apply(lambda x: "أنثى" if str(x) == "1" else "ذكر")

        total_pages = max(1, math.ceil(total_rows / page_size))

        # ✅ عرض النتائج
        st.dataframe(df, use_container_width=True, height=500)

        c1, c2, c3 = st.columns([1,2,1])
        with c1:
            if st.button("⬅️ السابق", disabled=(st.session_state.page <= 1)):
                st.session_state.page -= 1
                st.experimental_rerun()
        with c2:
            st.markdown(
                f"<div style='text-align:center;font-weight:bold'>صفحة {st.session_state.page} من {total_pages}</div>",
                unsafe_allow_html=True
            )
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
                SELECT "رقم الناخب","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                       "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
                FROM {table_name}
                WHERE "رقم الناخب" = %s
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
                    "رقم المحطة": "رقم المحطة"
                })
                df["الجنس"] = df["الجنس"].apply(lambda x: "أنثى" if str(x) == "1" else "ذكر")

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

    uploaded_file = st.file_uploader("📤 ارفع ملف (يحتوي على عمود رقم الناخب)", type=["xlsx"])

    if uploaded_file and st.button("🚀 تشغيل البحث"):
        try:
            voters_df = pd.read_excel(uploaded_file, engine="openpyxl")

            # التأكد من وجود العمود
            voter_col = "رقم الناخب" if "رقم الناخب" in voters_df.columns else "VoterNo"
            voters_list = voters_df[voter_col].astype(str).tolist()

            conn = get_conn()
            placeholders = ",".join(["%s"] * len(voters_list))
            query = f"""
                SELECT "رقم الناخب","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                       "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
                FROM {table_name}
                WHERE "رقم الناخب" IN ({placeholders})
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
                    "رقم المحطة": "رقم المحطة"
                })
                df["الجنس"] = df["الجنس"].apply(lambda x: "أنثى" if str(x) == "1" else "ذكر")

                # ✅ إضافة الأعمدة الإضافية
                df["رقم المندوب الرئيسي"] = ""
                df["الحالة"] = 0
                df["ملاحظة"] = ""

                # ✅ إعادة ترتيب الأعمدة حسب الستركشر المطلوب
                df = df[[
                    "رقم الناخب","الاسم","الجنس","رقم الهاتف","رقم العائلة",
                    "مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة",
                    "رقم المندوب الرئيسي","الحالة","ملاحظة"
                ]]

                # عرض النتائج
                st.dataframe(df, use_container_width=True, height=500)

                # ملف النتائج
                output_file = "نتائج_البحث.xlsx"
                df.to_excel(output_file, index=False, engine="openpyxl")
                with open(output_file, "rb") as f:
                    st.download_button("⬇️ تحميل النتائج", f,
                        file_name="نتائج_البحث.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                # ✅ الأرقام غير الموجودة
                found_numbers = set(df["رقم الناخب"].astype(str).tolist())
                missing_numbers = [num for num in voters_list if num not in found_numbers]

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

    imgs = st.file_uploader(
        "📤 ارفع صور البطاقات (سيتم استخراج رقم الناخب والبحث في قاعدة البيانات)",
        type=["jpg","jpeg","png"],
        accept_multiple_files=True
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

            if results:
                st.markdown("### 🖼️ الصور التي تحتوي أرقام ناخب:")
                for r in results:
                    st.image(r["content"], caption=f"{r['filename']} — الأرقام: {', '.join(r['numbers'])}", use_column_width=True)

            if all_voters:
                try:
                    conn = get_conn()
                    placeholders = ",".join(["%s"] * len(all_voters))
                    query = f"""
                        SELECT "رقم الناخب","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                               "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
                        FROM {table_name}
                        WHERE "رقم الناخب" IN ({placeholders})
                    """
                    df = pd.read_sql_query(query, conn, params=all_voters)
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
                            "رقم المحطة": "رقم المحطة"
                        })
                        df["الجنس"] = df["الجنس"].apply(lambda x: "أنثى" if str(x) == "1" else "ذكر")

                        # ✅ إضافة الأعمدة الإضافية
                        df["رقم المندوب الرئيسي"] = ""
                        df["الحالة"] = 0
                        df["ملاحظة"] = ""

                        df = df[[
                            "رقم الناخب","الاسم","الجنس","رقم الهاتف","رقم العائلة",
                            "مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة",
                            "رقم المندوب الرئيسي","الحالة","ملاحظة"
                        ]]

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
                st.warning("⚠️ لم يتم التعرف على أي أرقام في الصور")
# ----------------------------------------------------------------------------- #
# 5) 📦 عدّ البطاقات (أرقام 8 خانات) + بحث في القاعدة + قائمة الأرقام غير الموجودة
# ----------------------------------------------------------------------------- #
with tab_count:
    st.subheader("📦 عدّ البطاقات (أرقام 8 خانات) — بحث في القاعدة + الأرقام غير الموجودة")

    imgs_count = st.file_uploader(
        "📤 ارفع صور الصفحات (قد تحتوي أكثر من بطاقة)",
        type=["jpg","jpeg","png"],
        accept_multiple_files=True
    )

    if imgs_count and st.button("🚀 عدّ البطاقات والبحث"):
        client = setup_google_vision()
        if client is None:
            st.error("❌ خطأ في إعداد Google Vision.")
        else:
            all_numbers = []
            number_to_files = {}
            details = []

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
                        "عدد البطاقات (أرقام 8 خانات)": len(found_numbers),
                        "الأرقام المكتشفة (8 خانات فقط)": ", ".join(found_numbers) if found_numbers else "لا يوجد"
                    })

                except Exception as e:
                    st.warning(f"⚠️ خطأ أثناء معالجة صورة {img.name}: {e}")

            total_cards = len(all_numbers)
            unique_numbers = sorted(list(set(all_numbers)))

            st.success("✅ تم الاستخراج الأولي للأرقام")
            st.metric("إجمالي الأرقام (مع التكرار)", total_cards)
            st.metric("إجمالي الأرقام الفريدة (8 خانات)", len(unique_numbers))
            st.metric("عدد الصور المرفوعة", len(imgs_count))

            # ----------------- بحث في قاعدة البيانات -----------------
            found_df = pd.DataFrame()
            missing_list = []
            if unique_numbers:
                try:
                    conn = get_conn()
                    placeholders = ",".join(["%s"] * len(unique_numbers))
                    query = f"""
                        SELECT "رقم الناخب","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                               "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
                        FROM {table_name}
                        WHERE "رقم الناخب" IN ({placeholders})
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
                            "رقم المحطة": "رقم المحطة"
                        })
                        found_df["الجنس"] = found_df["الجنس"].apply(lambda x: "أنثى" if str(x) == "1" else "ذكر")

                        # ✅ إضافة الأعمدة الإضافية
                        found_df["رقم المندوب الرئيسي"] = ""
                        found_df["الحالة"] = 0
                        found_df["ملاحظة"] = ""

                        found_df = found_df[[
                            "رقم الناخب","الاسم","الجنس","رقم الهاتف","رقم العائلة",
                            "مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة",
                            "رقم المندوب الرئيسي","الحالة","ملاحظة"
                        ]]

                    found_numbers_in_db = set(found_df["رقم الناخب"].astype(str).tolist()) if not found_df.empty else set()
                    for n in unique_numbers:
                        if n not in found_numbers_in_db:
                            files = sorted(list(number_to_files.get(n, [])))
                            missing_list.append({"رقم_الناخب": n, "المصدر(الصور)": ", ".join(files)})
                except Exception as e:
                    st.error(f"❌ خطأ أثناء البحث في قاعدة البيانات: {e}")

            # ----------------- عرض النتائج -----------------
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
                st.success("✅ لا توجد أرقام مفقودة (كل الأرقام موجودة في القاعدة).")
