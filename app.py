import os
import pandas as pd
import streamlit as st
import psycopg2
from openpyxl import load_workbook
from dotenv import load_dotenv

# تحميل متغيرات البيئة من ملف .env
load_dotenv()

# إعداد الصفحة
st.set_page_config(page_title="المراقب الذكي", layout="wide")
st.title("📊 المراقب الذكي - البحث في سجلات الناخبين")
st.markdown("سيتم البحث في قواعد البيانات باستخدام الذكاء الاصطناعي 🤖")

# رفع ملف الناخبين
uploaded_voter_file = st.file_uploader("📂 ارفع ملف الناخبين (يحتوي على VoterNo أو رقم الناخب)", type=["xlsx"])

if uploaded_voter_file:
    if st.button("🚀 تشغيل البحث"):
        try:
            # قراءة ملف الناخبين
            voters_df = pd.read_excel(uploaded_voter_file, engine="openpyxl")
            if "VoterNo" not in voters_df.columns and "رقم الناخب" not in voters_df.columns:
                st.error("❌ ملف الناخبين يجب أن يحتوي على عمود VoterNo أو رقم الناخب")
            else:
                voter_col = "VoterNo" if "VoterNo" in voters_df.columns else "رقم الناخب"
                voters_list = voters_df[voter_col].astype(str).tolist()

                # الاتصال بقاعدة البيانات PostgreSQL باستخدام متغيرات البيئة
                conn = psycopg2.connect(
                    dbname=os.environ.get("DB_NAME"),
                    user=os.environ.get("DB_USER"),
                    password=os.environ.get("DB_PASSWORD"),
                    host=os.environ.get("DB_HOST"),
                    port=os.environ.get("DB_PORT"),
                    sslmode=os.environ.get("DB_SSLMODE")
                )

                placeholders = ",".join(["%s"] * len(voters_list))
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

                df = pd.read_sql_query(query, conn, params=voters_list)
                conn.close()

                if not df.empty:
                    # إعادة تسمية الأعمدة
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

                    # تعديل قيم الجنس
                    df["الجنس"] = df["الجنس"].apply(lambda x: "F" if str(x) == "1" else "M")

                    # إضافة أعمدة جديدة
                    df["رقم المندوب الرئيسي"] = ""
                    df["الحالة"] = 0
                    df["ملاحظة"] = ""

                    df = df[
                        ["رقم الناخب", "الاسم", "الجنس", "رقم الهاتف",
                         "رقم العائلة", "مركز الاقتراع", "رقم مركز الاقتراع",
                         "رقم المحطة", "رقم المندوب الرئيسي", "الحالة", "ملاحظة"]
                    ]

                    # حفظ النتائج
                    output_file = "نتائج_البحث.xlsx"
                    df.to_excel(output_file, index=False, engine="openpyxl")

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
