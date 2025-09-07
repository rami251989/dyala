import os
import pandas as pd
import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from openpyxl import load_workbook
from dotenv import load_dotenv

# تحميل متغيرات البيئة من ملف .env
load_dotenv()

# إعداد الصفحة
st.set_page_config(page_title="📊 المراقب الذكي", layout="wide")
st.title("📊 المراقب الذكي - البحث في سجلات الناخبين")
st.markdown("### ابحث باستخدام رقم الناخب مباشرة أو ارفع ملف Excel للبحث الجماعي 🤖")

# إنشاء اتصال بقاعدة البيانات
def get_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        sslmode="require",
        cursor_factory=RealDictCursor
    )

# دالة البحث
def search_voters(voter_numbers):
    conn = get_connection()
    try:
        query = """
        SELECT "VoterNo", "الاسم الثلاثي", "الجنس", "هاتف", "رقم العائلة",
               "اسم مركز الاقتراع", "رقم مركز الاقتراع", "رقم المحطة"
        FROM voters
        WHERE "VoterNo" = ANY(%s)
        """
        df = pd.read_sql(query, conn, params=(voter_numbers,))
        return df
    finally:
        conn.close()

# 🟢 خيار البحث المفرد
st.subheader("🔍 البحث برقم ناخب واحد")
voter_input = st.text_input("ادخل رقم الناخب:")

if st.button("بحث"):
    if voter_input.strip():
        result = search_voters([voter_input.strip()])
        if not result.empty:
            st.success(f"✅ تم العثور على {len(result)} نتيجة")
            st.dataframe(result, use_container_width=True)
        else:
            st.warning("⚠️ لم يتم العثور على نتائج لهذا الرقم")

# 🟢 خيار البحث عبر ملف Excel
st.subheader("📂 البحث عبر ملف Excel")
uploaded_voter_file = st.file_uploader("ارفع ملف Excel يحتوي على أرقام الناخبين", type=["xlsx"])

if uploaded_voter_file:
    if st.button("🚀 تشغيل البحث الجماعي"):
        try:
            voters_df = pd.read_excel(uploaded_voter_file, engine="openpyxl")
            if "VoterNo" not in voters_df.columns and "رقم الناخب" not in voters_df.columns:
                st.error("❌ ملف الناخبين يجب أن يحتوي على عمود VoterNo أو رقم الناخب")
            else:
                voter_col = "VoterNo" if "VoterNo" in voters_df.columns else "رقم الناخب"
                voters_list = voters_df[voter_col].astype(str).tolist()

                result = search_voters(voters_list)

                if not result.empty:
                    st.success(f"✅ تم العثور على {len(result)} نتيجة")
                    st.dataframe(result, use_container_width=True)

                    # حفظ الملف النهائي
                    output_file = "نتائج_البحث.xlsx"
                    result.to_excel(output_file, index=False, engine="openpyxl")

                    wb = load_workbook(output_file)
                    ws = wb.active
                    ws.sheet_view.rightToLeft = True
                    wb.save(output_file)

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
