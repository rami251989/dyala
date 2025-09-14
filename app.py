import os
import math
import pandas as pd
import streamlit as st
import psycopg2
from openpyxl import load_workbook
from dotenv import load_dotenv
from google.cloud import vision
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
tab_browse, tab_single, tab_file, tab_ocr = st.tabs(
    ["📄 تصفّح السجلات (Pagination)", "🔍 بحث برقم", "📂 رفع ملف Excel", "📸 رفع صور بطاقات"]
)

# ----------------------------------------------------------------------------- 
# 1) 📄 تصفّح السجلات
# ----------------------------------------------------------------------------- 
with tab_browse:
    # نفس الكود السابق تبع التصفح ...
    # (موجود عندك بدون تغيير)
    # -----------------------------
    st.subheader("📄 تصفّح السجلات مع فلاتر")
    if "page" not in st.session_state:
        st.session_state.page = 1
    if "filters" not in st.session_state:
        st.session_state.filters = {"voter": "", "name": "", "center": ""}

    # باقي الكود تبع التصفّح ... (كما عندك بالضبط)
    # -----------------------------

# ----------------------------------------------------------------------------- 
# 2) 🔍 البحث برقم واحد
# ----------------------------------------------------------------------------- 
with tab_single:
    # نفس الكود السابق تبع البحث ...
    # -----------------------------

# ----------------------------------------------------------------------------- 
# 3) 📂 رفع ملف Excel
# ----------------------------------------------------------------------------- 
with tab_file:
    # نفس الكود السابق تبع رفع ملف Excel ...
    # -----------------------------

# ----------------------------------------------------------------------------- 
# 4) 📸 رفع صور بطاقات الناخبين (Google Vision OCR)
# ----------------------------------------------------------------------------- 
with tab_ocr:
    st.subheader("📸 رفع صور بطاقات الناخبين")
    uploaded_images = st.file_uploader(
        "يمكنك رفع صورة أو أكثر", type=["jpg", "jpeg", "png"], accept_multiple_files=True
    )

    if uploaded_images and st.button("🚀 استخراج الأرقام والبحث"):
        try:
            # ---- إعداد Google Vision ----
            with open("google_vision.json", "w") as f:
                f.write(st.secrets["GOOGLE_VISION_KEY"])
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_vision.json"
            client = vision.ImageAnnotatorClient()

            all_voters = []

            for img in uploaded_images:
                content = img.read()
                image = vision.Image(content=content)
                response = client.text_detection(image=image)
                texts = response.text_annotations

                if texts:
                    full_text = texts[0].description
                    st.text_area(f"📄 النص المستخرج من {img.name}", full_text, height=150)

                    # استخراج أرقام الناخبين (6–10 أرقام متتالية)
                    numbers = re.findall(r"\b\d{6,10}\b", full_text)
                    if numbers:
                        st.success(f"🔢 الأرقام المستخرجة: {', '.join(numbers)}")
                        all_voters.extend(numbers)
                    else:
                        st.warning(f"⚠️ لم يتم العثور على رقم ناخب في {img.name}")

            if all_voters:
                # البحث عن الناخبين في قاعدة البيانات
                conn = get_conn()
                placeholders = ",".join(["%s"] * len(all_voters))
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
                df = pd.read_sql_query(query, conn, params=all_voters)
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
                    df["الجنس"] = df["الجنس"].apply(map_gender)

                    st.dataframe(df, use_container_width=True, height=500)

                    # تنزيل النتائج
                    output_file = "نتائج_البطاقات.xlsx"
                    df.to_excel(output_file, index=False, engine="openpyxl")

                    wb = load_workbook(output_file)
                    ws = wb.active
                    ws.sheet_view.rightToLeft = True
                    wb.save(output_file)

                    with open(output_file, "rb") as f:
                        st.download_button(
                            "⬇️ تحميل النتائج",
                            f,
                            file_name="نتائج_البطاقات.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                else:
                    st.warning("⚠️ لم يتم العثور على الناخبين في قاعدة البيانات")
        except Exception as e:
            st.error(f"❌ خطأ أثناء استخراج النصوص: {e}")
