import os
import pandas as pd
import streamlit as st
from openpyxl import load_workbook

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

                results = []
                data_folder = "data"
                files = [f for f in os.listdir(data_folder) if f.endswith(".xlsx")]
                progress = st.progress(0)

                for idx, file in enumerate(files, 1):
                    file_path = os.path.join(data_folder, file)
                    df = pd.read_excel(file_path, engine="openpyxl")

                    if "VoterNo" not in df.columns:
                        st.warning(f"{file} → لا يحتوي على VoterNo")
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
                        st.success(f"{file} → تم إيجاد {len(matches)} نتيجة")
                    else:
                        st.info(f"{file} → لا يوجد نتائج")

                    progress.progress(idx / len(files))

                if results:
                    final_df = pd.concat(results, ignore_index=True)

                    # حفظ الملف مؤقتًا
                    output_file = "نتائج_البحث.xlsx"
                    final_df.to_excel(output_file, index=False, engine="openpyxl")

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
