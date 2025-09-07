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


# البحث عن ناخبين باستخدام أرقام من ملف Excel
def search_voters(voter_numbers):
    conn = get_connection()
    query = 'SELECT * FROM voters WHERE "VoterNo" = ANY(%s);'
    df = pd.read_sql(query, conn, params=(voter_numbers,))
    conn.close()
    return df


# إعداد واجهة Streamlit
st.set_page_config(page_title="المراقب الذكي", layout="wide")

st.title("🗳️ المراقب الذكي - البحث عن الناخبين")
st.markdown("ابحث باستخدام ملف Excel يحتوي على أرقام الناخبين.")

# رفع ملف Excel
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
