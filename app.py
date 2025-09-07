import os
import pandas as pd
import streamlit as st
import psycopg2
from openpyxl import load_workbook
from dotenv import load_dotenv

# تحميل متغيرات البيئة من ملف .env أو من Streamlit Secrets
load_dotenv()

DB_NAME = os.getenv("DB_NAME", st.secrets.get("DB_NAME"))
DB_USER = os.getenv("DB_USER", st.secrets.get("DB_USER"))
DB_PASSWORD = os.getenv("DB_PASSWORD", st.secrets.get("DB_PASSWORD"))
DB_HOST = os.getenv("DB_HOST", st.secrets.get("DB_HOST"))
DB_PORT = os.getenv("DB_PORT", st.secrets.get("DB_PORT"))
DB_SSLMODE = os.getenv("DB_SSLMODE", st.secrets.get("DB_SSLMODE", "require"))

# إعداد الصفحة
st.set_page_config(page_title="المراقب الذكي", page_icon="🗳️", layout="wide")

# ديزاين العنوان
st.markdown(
    """
    <div style="text-align: center; padding: 20px; background: linear-gradient(90deg, #0052D4, #4364F7, #6FB1FC); border-radius: 12px;">
        <h1 style="color: white;">🗳️ المراقب الذكي</h1>
        <p style="color: white; font-size:18px;">ابحث في سجلات الناخبين باستخدام الذكاء الاصطناعي 🤖</p>
    </div>
    """,
    unsafe_allow_html=True
)

# الاتصال بقاعدة البيانات
def connect_db():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        sslmode=DB_SSLMODE
    )

# البحث في قاعدة البيانات
def search_voters(voter_numbers):
    conn = connect_db()
    query = f"""
        SELECT 
            "VoterNo" AS "رقم الناخب",
            "الاسم الثلاثي" AS "الاسم",
            CASE WHEN "الجنس" = '1' THEN 'F' ELSE 'M' END AS "الجنس",
            "هاتف" AS "رقم الهاتف",
            "رقم العائلة",
            "اسم مركز الاقتراع" AS "مركز الاقتراع",
            "رقم مركز الاقتراع",
            "رقم المحطة"
        FROM voters
        WHERE "VoterNo" = ANY(%s)
    """
    df = pd.read_sql(query, conn, params=(voter_numbers,))
    conn.close()

    if not df.empty:
        df["رقم المندوب الرئيسي"] = ""
        df["الحالة"] = 0
        df["ملاحظة"] = ""
        df = df[
            ["رقم الناخب", "الاسم", "الجنس", "رقم الهاتف",
             "رقم العائلة", "مركز الاقتراع", "رقم مركز الاقتراع",
             "رقم المحطة", "رقم المندوب الرئيسي", "الحالة", "ملاحظة"]
        ]
    return df

# واجهة المستخدم
tab1, tab2 = st.tabs(["🔍 بحث برقم ناخب", "📂 رفع ملف Excel"])

with tab1:
    st.subheader("🔍 البحث عن رقم ناخب")
    voter_input = st.text_input("أدخل رقم الناخب:")
    if st.button("🚀 بحث"):
        if voter_input.strip():
            result = search_voters([voter_input.strip()])
            if not result.empty:
                st.success(f"✅ تم العثور على {len(result)} نتيجة")
                st.dataframe(result, use_container_width=True)
            else:
                st.warning("⚠️ لم يتم العثور على نتائج")
        else:
            st.error("❌ الرجاء إدخال رقم ناخب")

with tab2:
    st.subheader("📂 البحث باستخدام ملف Excel")
    uploaded_voter_file = st.file_uploader("📂 ارفع ملف الناخبين", type=["xlsx"])

    if uploaded_voter_file and st.button("🚀 تشغيل البحث"):
        try:
            voters_df = pd.read_excel(uploaded_voter_file, engine="openpyxl")
            if "VoterNo" not in voters_df.columns and "رقم الناخب" not in voters_df.columns:
                st.error("❌ ملف الناخبين يجب أن يحتوي على عمود VoterNo أو رقم الناخب")
            else:
                voter_col = "VoterNo" if "VoterNo" in voters_df.columns else "رقم الناخب"
                voters_list = voters_df[voter_col].astype(str).tolist()

                final_df = search_voters(voters_list)

                if not final_df.empty:
                    output_file = "نتائج_البحث.xlsx"
                    final_df.to_excel(output_file, index=False, engine="openpyxl")

                    wb = load_workbook(output_file)
                    ws = wb.active
                    ws.sheet_view.rightToLeft = True
                    wb.save(output_file)

                    st.success(f"✅ تم العثور على {len(final_df)} نتيجة")
                    st.dataframe(final_df, use_container_width=True)

                    with open(output_file, "rb") as f:
                        st.download_button(
                            "⬇️ تحميل النتائج",
                            f,
                            file_name="نتائج_البحث.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                else:
                    st.warning("⚠️ لم يتم العثور على نتائج")
        except Exception as e:
            st.error(f"❌ خطأ: {e}")
