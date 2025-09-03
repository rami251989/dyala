import os
import pandas as pd
import streamlit as st
from io import BytesIO

# إعداد الواجهة
st.set_page_config(page_title="المراقب الذكي - البحث في سجلات الناخبين", layout="wide")

st.title("📊 المراقب الذكي - البحث في سجلات الناخبين")

# تحميل الملفات من مجلد data
DATA_FOLDER = "data"
files = [f for f in os.listdir(DATA_FOLDER) if f.endswith(".xlsx")]

# اختيار طريقة البحث
option = st.radio("اختر طريقة البحث:", ["🔼 رفع ملف Excel", "🔍 إدخال رقم ناخب"])

results = []

if option == "🔼 رفع ملف Excel":
    uploaded_file = st.file_uploader("ارفع ملف Excel يحتوي على عمود VoterNo", type=["xlsx"])
    if uploaded_file:
        voters_df = pd.read_excel(uploaded_file, engine="openpyxl")
        if "VoterNo" not in voters_df.columns and "رقم الناخب" not in voters_df.columns:
            st.error("⚠️ الملف يجب أن يحتوي على عمود VoterNo أو رقم الناخب")
        else:
            voter_col = "VoterNo" if "VoterNo" in voters_df.columns else "رقم الناخب"
            voters_list = voters_df[voter_col].astype(str).tolist()

elif option == "🔍 إدخال رقم ناخب":
    voter_id = st.text_input("أدخل رقم الناخب:")
    if st.button("بحث"):
        if voter_id.strip() != "":
            voters_list = [voter_id.strip()]
        else:
            st.warning("⚠️ يرجى إدخال رقم الناخب أولاً")
            voters_list = []
    else:
        voters_list = []

# البحث وتنفيذ النتائج
if "voters_list" in locals() and voters_list:
    for file in files:
        try:
            df = pd.read_excel(os.path.join(DATA_FOLDER, file), engine="openpyxl")
            if "VoterNo" not in df.columns:
                continue

            df["VoterNo"] = df["VoterNo"].astype(str)
            matches = df[df["VoterNo"].isin(voters_list)]

            if not matches.empty:
                matches = matches.rename(columns={
                    "VoterNo": "رقم الناخب",
                    "الاسم الثلاثي": "الاسم",
                    "الجنس": "الجنس",
                    "هاتف": "رقم الهاتف",
                    "رقم العائلة": "رقم العائلة",
                    "اسم مركز الاقتراع": "مركز الاقتراع",
                    "رقم مركز الاقتراع": "رقم مركز الاقتراع",
                    "رقم المحطة": "رقم المحطة"
                })

                matches["الجنس"] = matches["الجنس"].apply(lambda x: "F" if str(x) == "1" else "M")
                matches["رقم المندوب الرئيسي"] = ""
                matches["الحالة"] = 0
                matches["ملاحظة"] = ""

                matches = matches[
                    ["رقم الناخب", "الاسم", "الجنس", "رقم الهاتف",
                     "رقم العائلة", "مركز الاقتراع", "رقم مركز الاقتراع",
                     "رقم المحطة", "رقم المندوب الرئيسي", "الحالة", "ملاحظة"]
                ]

                results.append(matches)

        except Exception as e:
            st.error(f"خطأ في الملف {file}: {e}")

    if results:
        final_df = pd.concat(results, ignore_index=True)
        st.success(f"✅ تم العثور على {len(final_df)} نتيجة")
        st.dataframe(final_df, use_container_width=True)

        # زر تحميل النتائج
        buffer = BytesIO()
        final_df.to_excel(buffer, index=False, engine="openpyxl")
        buffer.seek(0)
        st.download_button(
            label="⬇️ تحميل النتائج",
            data=buffer,
            file_name="results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("ℹ️ لا يوجد نتائج مطابقة.")
