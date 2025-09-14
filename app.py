import streamlit as st
import pandas as pd
import psycopg2
import json
import os
from google.cloud import vision

# -----------------------------------------------------------
# 📌 إعداد الاتصال بقاعدة البيانات (Digital Ocean PostgreSQL)
# -----------------------------------------------------------
def get_connection():
    conn = psycopg2.connect(
        dbname=st.secrets["DB_NAME"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
        host=st.secrets["DB_HOST"],
        port=st.secrets["DB_PORT"],
        sslmode=st.secrets["DB_SSLMODE"]
    )
    return conn


# -----------------------------------------------------------
# 📌 دوال للتعامل مع قاعدة البيانات
# -----------------------------------------------------------
def search_voter(voter_number):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT voter_number, name, gender FROM voters WHERE voter_number = %s;", (voter_number,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result


def insert_voters(df):
    conn = get_connection()
    cur = conn.cursor()
    for _, row in df.iterrows():
        cur.execute(
            "INSERT INTO voters (voter_number, name, gender) VALUES (%s, %s, %s) ON CONFLICT (voter_number) DO NOTHING;",
            (row['voter_number'], row['name'], row['gender'])
        )
    conn.commit()
    cur.close()
    conn.close()


def fetch_all_voters():
    conn = get_connection()
    df = pd.read_sql("SELECT voter_number, name, gender FROM voters;", conn)
    conn.close()
    return df


# -----------------------------------------------------------
# 📌 إعداد Google Vision OCR
# -----------------------------------------------------------
with open("google_vision.json", "w") as f:
    f.write(st.secrets["GOOGLE_VISION_JSON"])

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "google_vision.json"
vision_client = vision.ImageAnnotatorClient()


def extract_text_from_image(uploaded_file):
    """استدعاء OCR من Google Vision"""
    content = uploaded_file.read()
    image = vision.Image(content=content)
    response = vision_client.text_detection(image=image)
    texts = response.text_annotations

    if not texts:
        return None

    full_text = texts[0].description.strip()
    return full_text


# -----------------------------------------------------------
# 📌 الواجهة الرئيسية (Streamlit App)
# -----------------------------------------------------------
st.set_page_config(page_title="📋 Voter Search App", layout="wide")

st.sidebar.title("📌 القائمة")
choice = st.sidebar.radio(
    "اختر الإجراء:",
    [
        "🏠 الصفحة الرئيسية",
        "🔍 البحث برقم الناخب",
        "📂 رفع ملف Excel",
        "📄 عرض جميع السجلات",
        "📸 رفع صور بطاقات الناخبين"
    ]
)

# -----------------------------------------------------------
# 🏠 الصفحة الرئيسية
# -----------------------------------------------------------
if choice == "🏠 الصفحة الرئيسية":
    st.title("📋 نظام إدارة بيانات الناخبين")
    st.markdown("""
    أهلاً بك 👋  
    هذا النظام يسمح لك بالقيام بالتالي:
    - 🔍 البحث برقم الناخب.
    - 📂 رفع ملفات Excel تحتوي بيانات الناخبين.
    - 📄 عرض كل السجلات.
    - 📸 رفع صورة بطاقة ناخب واستخراج الرقم عبر OCR.
    """)

# -----------------------------------------------------------
# 🔍 البحث برقم الناخب
# -----------------------------------------------------------
elif choice == "🔍 البحث برقم الناخب":
    st.header("🔍 البحث عن ناخب")

    voter_number = st.text_input("أدخل رقم الناخب:")
    if st.button("بحث"):
        if voter_number:
            result = search_voter(voter_number)
            if result:
                st.success(f"✅ الاسم: {result[1]} | الجنس: {result[2]} | الرقم: {result[0]}")
            else:
                st.error("❌ الناخب غير موجود.")
        else:
            st.warning("⚠️ يرجى إدخال رقم الناخب.")

# -----------------------------------------------------------
# 📂 رفع ملف Excel
# -----------------------------------------------------------
elif choice == "📂 رفع ملف Excel":
    st.header("📂 رفع ملف Excel")

    uploaded_file = st.file_uploader("ارفع ملف Excel يحتوي أعمدة: voter_number, name, gender", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        st.dataframe(df)

        if st.button("📥 حفظ في قاعدة البيانات"):
            insert_voters(df)
            st.success("✅ تم إدخال البيانات بنجاح.")

# -----------------------------------------------------------
# 📄 عرض جميع السجلات
# -----------------------------------------------------------
elif choice == "📄 عرض جميع السجلات":
    st.header("📄 جميع الناخبين")

    df = fetch_all_voters()
    st.dataframe(df)

# -----------------------------------------------------------
# 📸 رفع صور بطاقات الناخبين (OCR)
# -----------------------------------------------------------
elif choice == "📸 رفع صور بطاقات الناخبين":
    st.header("📸 استخراج رقم الناخب من صورة البطاقة")

    uploaded_img = st.file_uploader("ارفع صورة البطاقة (JPG أو PNG)", type=["jpg", "jpeg", "png"])
    if uploaded_img:
        st.image(uploaded_img, caption="📸 الصورة المرفوعة", use_column_width=True)

        if st.button("📝 استخراج النصوص"):
            extracted_text = extract_text_from_image(uploaded_img)

            if extracted_text:
                st.success("✅ النصوص المستخرجة:")
                st.text(extracted_text)

                # محاولة استخراج رقم ناخب (أرقام فقط)
                import re
                numbers = re.findall(r"\d+", extracted_text)
                if numbers:
                    voter_number = numbers[0]
                    st.info(f"🔎 تم التعرف على رقم ناخب: **{voter_number}**")

                    # البحث في قاعدة البيانات
                    result = search_voter(voter_number)
                    if result:
                        st.success(f"✅ موجود في قاعدة البيانات: {result[1]} | {result[2]}")
                    else:
                        st.warning("⚠️ الرقم غير موجود في قاعدة البيانات.")
                else:
                    st.error("❌ لم يتم العثور على رقم ناخب.")
            else:
                st.error("❌ لم يتم التعرف على أي نص من الصورة.")
