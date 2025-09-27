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

# ---- اختيار المدينة (يحدد الجدول) ----
# لديك جدولان رئيسيان: "Bagdad" و"Babil" (يمكنك تعديل القائمة حسب الحاجة)
city = st.selectbox("🏙️ اختر المدينة (الجدول)", ["Bagdad", "Babil"])
table_name = f'"{city}"'  # سيُستخدم في كل الاستعلامات لاحقاً
st.caption(f"سيتم الاستعلام من الجدول: {table_name}")
# ----------------------------------------------------------------------------- #
# 🔍 البحث برقم واحد
# ----------------------------------------------------------------------------- #
st.header("🔍 البحث برقم واحد")

voter_input = st.text_input("ادخل رقم الناخب:")

if st.button("بحث"):
    try:
        conn = get_conn()
        query = f"""
            SELECT "VoterNo","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                   "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
            FROM {table_name}
            WHERE "VoterNo" = %s
        """
        df = pd.read_sql_query(query, conn, params=(voter_input.strip(),))
        conn.close()

        if not df.empty:
            df = format_results(df)
            st.dataframe(df, use_container_width=True, height=500)
        else:
            st.warning("⚠️ لم يتم العثور على نتائج")
    except Exception as e:
        st.error(f"❌ خطأ: {e}")

# ----------------------------------------------------------------------------- #
# 📂 رفع ملف Excel (لائحة أرقام الناخبين)
# ----------------------------------------------------------------------------- #
st.header("📂 البحث باستخدام ملف Excel")

uploaded_file = st.file_uploader("📤 ارفع ملف يحتوي على أرقام الناخبين", type=["xlsx"])

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
            FROM {table_name}
            WHERE "VoterNo" IN ({placeholders})
        """
        df = pd.read_sql_query(query, conn, params=voters_list)
        conn.close()

        if not df.empty:
            df = format_results(df)

            # ✅ عرض النتائج
            st.dataframe(df, use_container_width=True, height=500)

            # ✅ تصدير النتائج
            output_file = "نتائج_البحث.xlsx"
            df.to_excel(output_file, index=False, engine="openpyxl")
            wb = load_workbook(output_file)
            wb.active.sheet_view.rightToLeft = True
            wb.save(output_file)
            with open(output_file, "rb") as f:
                st.download_button(
                    "⬇️ تحميل النتائج",
                    f,
                    file_name="نتائج_البحث.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            # ✅ إيجاد الأرقام غير الموجودة
            found_numbers = set(df["رقم الناخب"].astype(str).tolist())
            missing_numbers = [num for num in voters_list if num not in found_numbers]

            if missing_numbers:
                st.warning("⚠️ الأرقام التالية لم يتم العثور عليها في قاعدة البيانات:")
                st.write(missing_numbers)

                missing_df = pd.DataFrame(missing_numbers, columns=["الأرقام غير الموجودة"])
                miss_file = "missing_numbers.xlsx"
                missing_df.to_excel(miss_file, index=False, engine="openpyxl")
                with open(miss_file, "rb") as f:
                    st.download_button(
                        "⬇️ تحميل الأرقام غير الموجودة",
                        f,
                        file_name="الأرقام_غير_الموجودة.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
        else:
            st.warning("⚠️ لا يوجد نتائج")
    except Exception as e:
        st.error(f"❌ خطأ: {e}")
# ----------------------------------------------------------------------------- #
# 📸 OCR صور بطاقات
# ----------------------------------------------------------------------------- #
st.header("📸 OCR صور بطاقات")

# ---- قسم: استخراج الأرقام فقط ----
st.subheader("🔎 استخراج الأرقام فقط (بدون البحث في قاعدة البيانات)")

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
        results = []

        for img in imgs_only:
            try:
                content = img.read()
                image = vision.Image(content=content)
                response = client.text_detection(image=image)
                texts = response.text_annotations
                if texts:
                    found = re.findall(r"\b\d{6,10}\b", texts[0].description)
                    if found:
                        clear_numbers.extend(found)
                        results.append({"filename": img.name, "numbers": found})
            except Exception as e:
                st.warning(f"⚠️ خطأ أثناء معالجة صورة {img.name}: {e}")

        clear_numbers = list(dict.fromkeys(clear_numbers))

        if results:
            st.markdown("### 🖼️ الصور التي تحتوي أرقام ناخب:")
            for r in results:
                st.write(f"📌 {r['filename']} → {', '.join(r['numbers'])}")

        st.success("✅ تم استخراج الأرقام")
        st.write(clear_numbers)

        if clear_numbers:
            df_clear = pd.DataFrame(clear_numbers, columns=["الأرقام المستخرجة"])
            file_clear = "ocr_clear_numbers.xlsx"
            df_clear.to_excel(file_clear, index=False, engine="openpyxl")
            with open(file_clear, "rb") as f:
                st.download_button(
                    "⬇️ تحميل الأرقام المستخرجة",
                    f,
                    file_name="ocr_clear_numbers.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

st.markdown("---")

# ---- قسم: استخراج + البحث ----
st.subheader("🔎 استخراج الأرقام + البحث في قاعدة البيانات")

imgs = st.file_uploader(
    "📤 ارفع صور البطاقات (سيتم استخراج الأرقام والبحث)",
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
        for img in imgs:
            try:
                content = img.read()
                image = vision.Image(content=content)
                response = client.text_detection(image=image)
                texts = response.text_annotations
                if texts:
                    found = re.findall(r"\b\d{6,10}\b", texts[0].description)
                    all_voters.extend(found)
            except Exception as e:
                st.warning(f"⚠️ خطأ أثناء معالجة صورة {img.name}: {e}")

        if all_voters:
            try:
                conn = get_conn()
                placeholders = ",".join(["%s"] * len(all_voters))
                query = f"""
                    SELECT "VoterNo","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                           "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
                    FROM {table_name}
                    WHERE "VoterNo" IN ({placeholders})
                """
                df = pd.read_sql_query(query, conn, params=all_voters)
                conn.close()

                if not df.empty:
                    df = format_results(df)

                    # ✅ عرض النتائج
                    st.dataframe(df, use_container_width=True, height=500)

                    # ✅ تصدير النتائج
                    output_file = "ocr_نتائج_البحث.xlsx"
                    df.to_excel(output_file, index=False, engine="openpyxl")
                    wb = load_workbook(output_file)
                    wb.active.sheet_view.rightToLeft = True
                    wb.save(output_file)
                    with open(output_file, "rb") as f:
                        st.download_button(
                            "⬇️ تحميل النتائج OCR",
                            f,
                            file_name="ocr_نتائج_البحث.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                else:
                    st.warning("⚠️ لم يتم العثور على نتائج")
            except Exception as e:
                st.error(f"❌ خطأ أثناء البحث في قاعدة البيانات: {e}")
        else:
            st.warning("⚠️ لم يتم استخراج أي أرقام من الصور")
# ----------------------------------------------------------------------------- #
# 📦 عدّ البطاقات (أرقام 8 خانات) + بحث في القاعدة + قائمة الأرقام غير الموجودة
# ----------------------------------------------------------------------------- #
st.header("📦 عدّ البطاقات (أرقام 8 خانات)")

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
        all_numbers = []               # كل الأرقام المستخرجة (مع التكرار)
        number_to_files = {}           # ربط رقم الناخب → أسماء الملفات
        details = []                   # تفاصيل العرض

        for img in imgs_count:
            try:
                content = img.read()
                image = vision.Image(content=content)
                response = client.text_detection(image=image)
                texts = response.text_annotations
                full_text = texts[0].description if texts else ""

                # ✅ استخراج الأرقام المكونة من 8 خانات فقط
                found_numbers = re.findall(r"\b\d{8}\b", full_text)
                for n in found_numbers:
                    all_numbers.append(n)
                    number_to_files.setdefault(n, set()).add(img.name)

                details.append({
                    "اسم الملف": img.name,
                    "عدد الأرقام (8 خانات)": len(found_numbers),
                    "الأرقام": ", ".join(found_numbers) if found_numbers else "لا يوجد"
                })

            except Exception as e:
                st.warning(f"⚠️ خطأ أثناء معالجة صورة {img.name}: {e}")

        total_cards = len(all_numbers)
        unique_numbers = sorted(list(set(all_numbers)))

        st.success("✅ تم استخراج الأرقام")
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
                    SELECT "VoterNo","الاسم الثلاثي","الجنس","هاتف","رقم العائلة",
                           "اسم مركز الاقتراع","رقم مركز الاقتراع","رقم المحطة"
                    FROM {table_name}
                    WHERE "VoterNo" IN ({placeholders})
                """
                found_df = pd.read_sql_query(query, conn, params=unique_numbers)
                conn.close()

                if not found_df.empty:
                    found_df = format_results(found_df)

                found_numbers_in_db = set(found_df["رقم الناخب"].astype(str).tolist()) if not found_df.empty else set()

                for n in unique_numbers:
                    if n not in found_numbers_in_db:
                        files = sorted(list(number_to_files.get(n, [])))
                        missing_list.append({
                            "رقم_الناخب": n,
                            "المصدر (الصور)": ", ".join(files)
                        })

            except Exception as e:
                st.error(f"❌ خطأ أثناء البحث في قاعدة البيانات: {e}")
        else:
            st.info("ℹ️ لم يتم العثور على أرقام مكونة من 8 خانات في الصور المرفوعة.")

        # ----------------- عرض النتائج -----------------
        st.markdown("### 🔎 بيانات الناخبين (الموجودة في القاعدة)")
        if not found_df.empty:
            st.dataframe(found_df, use_container_width=True, height=400)
            out_found = "found_voters.xlsx"
            found_df.to_excel(out_found, index=False, engine="openpyxl")
            with open(out_found, "rb") as f:
                st.download_button("⬇️ تحميل بيانات الناخبين", f,
                    file_name="بيانات_الناخبين.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.warning("⚠️ لم يتم العثور على نتائج في قاعدة البيانات.")

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
            st.success("✅ جميع الأرقام المستخرجة موجودة في قاعدة البيانات.")
