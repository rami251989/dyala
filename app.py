import streamlit as st
import pandas as pd
from openpyxl import load_workbook
import io
import os

# ---------------- أدوات مساعدة ----------------
DATA_FOLDER = "data"

@st.cache_data
def load_data():
    results = []
    if not os.path.exists(DATA_FOLDER):
        return pd.DataFrame()
    for file in os.listdir(DATA_FOLDER):
        if file.endswith(".xlsx"):
            try:
                df = pd.read_excel(os.path.join(DATA_FOLDER, file), engine="openpyxl")
                if "VoterNo" in df.columns:
                    # إعادة تسمية
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
                    # تحويل الجنس
                    df["الجنس"] = df["الجنس"].apply(lambda x: "F" if str(x) == "1" else "M")

                    # إضافة أعمدة
                    df["رقم المندوب الرئيسي"] = ""
                    df["الحالة"] = 0
                    df["ملاحظة"] = ""

                    # ترتيب
                    df = df[["رقم الناخب", "الاسم", "الجنس", "رقم الهاتف",
                             "رقم العائلة", "مركز الاقتراع", "رقم مركز الاقتراع",
                             "رقم المحطة", "رقم المندوب الرئيسي", "الحالة", "ملاحظة"]]
                    results.append(df)
            except Exception as e:
                st.write(f"خطأ في قراءة {file}: {e}")
    if results:
        return pd.concat(results, ignore_index=True)
    return pd.DataFrame()

# ---------------- واجهة ----------------
st.set_page_config(page_title="المراقب الذكي", layout="wide")
st.title("📊 المراقب الذكي - البحث في سجلات الناخبين")

option = st.radio("اختر طريقة البحث:", ["📂 رفع ملف Excel", "🔍 إدخال رقم ناخب"])

data = load_data()

if option == "📂 رفع ملف Excel":
    uploaded_file = st.file_uploader("📂 ارفع ملف Excel يحتوي على عمود VoterNo", type=["xlsx"])
    if uploaded_file:
        voter_file = pd.read_excel(uploaded_file, engine="openpyxl")
        if "VoterNo" in voter_file.columns or "رقم الناخب" in voter_file.columns:
            voter_col = "VoterNo" if "VoterNo" in voter_file.columns else "رقم الناخب"
            voters_list = voter_file[voter_col].astype(str).tolist()

            if st.button("بحث"):
                matches = data[data["رقم الناخب"].astype(str).isin(voters_list)]
                if not matches.empty:
                    st.success(f"✅ تم العثور على {len(matches)} نتيجة")
                    st.dataframe(matches)

                    # زر تحميل
                    towrite = io.BytesIO()
                    matches.to_excel(towrite, index=False, engine="openpyxl")
                    towrite.seek(0)
                    st.download_button("⬇️ تحميل النتائج", towrite, file_name="results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                else:
                    st.warning("⚠️ لا يوجد نتائج")

elif option == "🔍 إدخال رقم ناخب":
    voter_no = st.text_input("🔢 أدخل رقم الناخب:")
    if st.button("بحث"):
        if voter_no:
            matches = data[data["رقم الناخب"].astype(str) == str(voter_no)]
            if not matches.empty:
                st.success("✅ تم العثور على نتيجة")
                st.dataframe(matches)

                # زر تحميل
                towrite = io.BytesIO()
                matches.to_excel(towrite, index=False, engine="openpyxl")
                towrite.seek(0)
                st.download_button("⬇️ تحميل النتيجة", towrite, file_name="result.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.warning("⚠️ لا يوجد نتائج")
        else:
            st.error("❌ يرجى إدخال رقم ناخب")
