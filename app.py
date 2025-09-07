import os
import pandas as pd
import streamlit as st
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "sslmode": os.getenv("DB_SSLMODE", "require")
}

# دالة للاتصال
def get_connection():
    return psycopg2.connect(**DB_CONFIG)

# دالة البحث
def search_voters(voter_numbers):
    conn = get_connection()
    try:
        query = sql.SQL("SELECT * FROM voters WHERE VoterNo IN %s")
        with conn.cursor() as cur:
            cur.execute(query, (tuple(voter_numbers),))
            cols = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()

# واجهة التطبيق
st.set_page_config(page_title="المراقب الذكي", layout="wide")
st.title("📊 المراقب الذكي - البحث في سجلات الناخبين")

tab1, tab2 = st.tabs(["🔍 بحث برقم الناخب", "📂 رفع ملف Excel"])

with tab1:
    voter_input = st.text_input("ادخل رقم الناخب:")
    if st.button("بحث", key="search_one"):
        if voter_input.strip():
            result = search_voters([voter_input.strip()])
            if not result.empty:
                st.success("✅ تم العثور على نتيجة")
                st.dataframe(result)
            else:
                st.warning("⚠️ لم يتم العثور على أي نتائج")

with tab2:
    uploaded_voter_file = st.file_uploader("📂 ارفع ملف الناخبين (يحتوي على VoterNo)", type=["xlsx"])
    if uploaded_voter_file and st.button("بحث", key="search_file"):
        voters_df = pd.read_excel(uploaded_voter_file, engine="openpyxl")
        if "VoterNo" not in voters_df.columns and "رقم الناخب" not in voters_df.columns:
            st.error("❌ الملف يجب أن يحتوي على عمود VoterNo أو رقم الناخب")
        else:
            voter_col = "VoterNo" if "VoterNo" in voters_df.columns else "رقم الناخب"
            voters_list = voters_df[voter_col].astype(str).tolist()
            result = search_voters(voters_list)
            if not result.empty:
                st.success(f"✅ تم العثور على {len(result)} نتيجة")
                st.dataframe(result)
            else:
                st.warning("⚠️ لم يتم العثور على أي نتائج")
