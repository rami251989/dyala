import os
import pandas as pd
import streamlit as st
import psycopg2
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")


# الاتصال بقاعدة البيانات
def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )


# دالة للحصول على أسماء الأعمدة بالجدول
def get_table_columns():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'voters';
    """)
    cols = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return cols


# البحث عن ناخب
def search_voters(voter_numbers):
    conn = get_connection()
    query = 'SELECT * FROM voters WHERE "VoterNo" = ANY(%s);'  # ✨ عدل الاسم إذا العمود غير
    df = pd.read_sql(query, conn, params=(voter_numbers,))
    conn.close()
    return df


# إعداد واجهة Streamlit
st.set_page_config(page_title="المراقب الذكي", layout="wide")

st.title("🗳️ المراقب الذكي - البحث عن الناخبين")
st.markdown("ابحث باستخدام رقم الناخب أو ارفع ملف Excel يحتوي على أرقام الناخبين.")

# 🔍 عرض أسماء الأعمدة من الجدول (للتأكد)
st.subheader("📋 الأعمدة الموجودة بجدول voters:")
columns = get_table_columns()
st.write(columns)

# اختيار بين البحث الفردي أو رفع ملف
tab1, tab2 = st.tabs(["🔎 بحث برقم الناخب", "📂 رفع ملف Excel"])

with tab1:
    voter_input = st.text_input("ادخال رقم الناخب:")
    if st.button("بحث"):
        if voter_input.strip():
            try:
                result = search_voters([voter_input.strip()])
                if result.empty:
                    st.warning("⚠️ ما في نتائج لهذا الرقم.")
                else:
                    st.success("✅ تم العثور على الناخب:")
                    st.dataframe(result)
            except Exception as e:
                st.error(f"Database error: {e}")
        else:
            st.warning("⚠️ الرجاء إدخال رقم الناخب.")

with tab2:
    uploaded_voter_file = st.file_uploader("📂 ارفع ملف Excel فيه أرقام الناخبين", type=["xlsx"])
    if uploaded_voter_file is not None:
        try:
            voters_df = pd.read_excel(uploaded_voter_file, engine="openpyxl")
            if "VoterNo" not in voters_df.columns:
                st.error("⚠️ ملف Excel لازم يحتوي على عمود باسم 'VoterNo'")
            else:
                voters_list = voters_df["VoterNo"].astype(str).tolist()
                result = search_voters(voters_list)
                if result.empty:
                    st.warning("⚠️ ما في نتائج للأرقام المرفوعة.")
                else:
                    st.success("✅ تم العثور على الناخبين:")
                    st.dataframe(result)
        except Exception as e:
            st.error(f"File error: {e}")
