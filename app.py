import streamlit as st
import pandas as pd
import os
from io import BytesIO
from openpyxl import load_workbook

# ----------------- عنوان التطبيق -----------------
st.set_page_config(page_title="المراقب الذكي", layout="wide")
st.title("📊 المراقب الذكي - البحث في سجلات الناخبين")

# ----------------- اختيار طريقة البحث -----------------
search_mode = st.radio(
    "اختر طريقة البحث:",
    ["📂 رفع ملف Excel", "🔍 إدخال رقم ناخب"]
)

def process_results(matches):
    if not matches.empty:
        # إعادة تسمية الأعمدة
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

        # تحويل الجنس 1=F, 0=M
        matches["الجنس"] = matches["الجنس"].apply(lambda x: "F" if str(x) == "1" else "M")

        # إضافة أعمدة إضافية
        matches["رقم المندوب الرئيسي"] = ""
        matches["الحالة"] = 0
        matches["ملاحظة"] = ""

        # ترتيب الأعمدة
        matches = matches[
            ["رقم الناخب", "الاسم", "الجنس", "رقم الهاتف",
             "رقم العائلة", "مركز الاقتراع", "رقم مركز الاقتراع",
             "رقم المحطة", "رقم المندوب الرئيسي", "الحالة", "ملاحظة"]
        ]
    return matches

def search_voters(voters_list):
    results = []
    data_folder = "data"
    files = [f for f in os.listdir(data_folder) if f.endswith(".xlsx")]

    for file in files:
        file_path = os.path.join(data_folder, file)
        try:
            df = pd.read_excel(file_path, engine="openpyxl")

            if "VoterNo" not in df.columns:
                continue

            df["VoterNo"] = df["VoterNo"].astype(str)
            matches = df[df["VoterNo"].isin(voters_list)]

            if not matches.empty:
                matches = process_results(matches)
                results.append(matches)

        except Exception as e:
            st.error(f"خطأ في قراءة {file}: {str(e)}")

    if results:
        return pd.concat(results, ignore_index=True)
    else:
        return pd.DataFrame()

# ----------------- البحث برفع ملف -----------------
if search_mode == "📂 رفع ملف Excel":
    uploaded_file = st.file_uploader("📂 ارفع ملف Excel يحتوي على عمود VoterNo", type=["xlsx"])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file, engine="openpyxl")
        if "VoterNo" in df.columns or "رقم الناخب" in df.columns:
            voter_col = "VoterNo" if "VoterNo" in df.columns else "رقم الناخب"
            voters_list = df[voter_col].astype(str).tolist()

            if st.button("بحث"):
                results = search_voters(voters_list)
                if not results.empty:
                    st.success(f"✅ تم العثور على {len(results)} نتيجة")
                    st.dataframe(results)

                    # زر تحميل
                    output = BytesIO()
                    results.to_excel(output, index=False, engine="openpyxl")
                    wb = load_workbook(output)
                    ws = wb.active
                    ws.sheet_view.rightToLeft = True
                    output2 = BytesIO()
                    wb.save(output2)

                    st.download_button(
                        label="⬇️ تحميل النتائج Excel",
                        data=output2.getvalue(),
                        file_name="نتائج_البحث.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("⚠️ لم يتم العثور على نتائج.")

# ----------------- البحث برقم ناخب -----------------
elif search_mode == "🔍 إدخال رقم ناخب":
    voter_no = st.text_input("📝 أدخل رقم الناخب:")
    if st.button("بحث"):
        if voter_no.strip() == "":
            st.error("❌ يرجى إدخال رقم ناخب")
        else:
            results = search_voters([voter_no.strip()])
            if not results.empty:
                st.success(f"✅ تم العثور على {len(results)} نتيجة")
                st.dataframe(results)

                # زر تحميل
                output = BytesIO()
                results.to_excel(output, index=False, engine="openpyxl")
                wb = load_workbook(output)
                ws = wb.active
                ws.sheet_view.rightToLeft = True
                output2 = BytesIO()
                wb.save(output2)

                st.download_button(
                    label="⬇️ تحميل النتائج Excel",
                    data=output2.getvalue(),
                    file_name="نتائج_البحث.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("⚠️ لم يتم العثور على نتائج.")
