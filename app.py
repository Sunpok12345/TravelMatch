"""
TravelMatch - ระบบแนะนำสถานที่ท่องเที่ยวที่เหมาะสมกับงบประมาณ ระยะเวลา และความสนใจของผู้ใช้

โครงสร้างของไฟล์นี้ถูกออกแบบให้ "ตรงกับรายงาน" ตามตาราง Mapping ในภาคผนวก:

    ในรายงาน                      ในโปรแกรม (ไฟล์นี้)
    -------------------------     ------------------------------
    Dataset                       travel_data.csv
    Data Preparation              pandas (load_data)
    ปัจจัยความสนใจ      40%       calculate_interest_score()
    ปัจจัยงบประมาณ      30%       calculate_budget_score()
    ปัจจัยระยะเวลา      20%       calculate_duration_score()
    คะแนนรีวิว           10%       calculate_review_score()
    Weighted Scoring              calculate_score()
    Ranking                       sort_values()
    ระบบแนะนำ                     Top 5
    Application                   Streamlit (ไฟล์นี้ทั้งไฟล์)

วิธีรัน:
    pip install streamlit pandas numpy
    streamlit run app.py
"""
import pandas as pd
import numpy as np
import streamlit as st

# ----------------------------------------------------------------------
# ค่าคงที่ของน้ำหนักปัจจัย (ต้องตรงกับที่ระบุในบทที่ 3 ของรายงานเป๊ะๆ)
# ----------------------------------------------------------------------
WEIGHT_INTEREST = 0.40   # ปัจจัยความสนใจ 40%
WEIGHT_BUDGET = 0.30     # ปัจจัยงบประมาณ 30%
WEIGHT_DURATION = 0.20   # ปัจจัยระยะเวลา 20%
WEIGHT_REVIEW = 0.10     # คะแนนรีวิว 10%

TOP_N = 5                # ระบบแนะนำ Top 5

DATA_PATH = "travel_data.csv"

# วางลิงก์รูปแบนเนอร์ของคุณตรงนี้ (เช่น รูปจาก imgur, unsplash, หรือรูปที่อัปโหลดขึ้น GitHub แล้วก็อปลิงก์ raw มาวาง)
# ถ้าไม่ต้องการแบนเนอร์ ให้ปล่อยเป็นสตริงว่าง ""
BANNER_IMAGE_URL = "https://i.pinimg.com/736x/4e/7b/01/4e7b01b29b205dceaf008fe80440e226.jpg"


# ----------------------------------------------------------------------
# 1) Data Preparation (บทที่ 3.3 ข้อมูลที่ใช้ในระบบ)
#    ใช้ Pandas อ่านและตรวจสอบข้อมูลเบื้องต้น (missing value, dtype)
# ----------------------------------------------------------------------
@st.cache_data
def load_data(path: str = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)

    # ตรวจสอบและจัดการค่าว่าง (Data Cleaning ตามหลักวิทยาการข้อมูล)
    df = df.dropna(subset=["place_name", "cost_per_person", "suggested_days", "review_score"])

    # แปลงชนิดข้อมูลให้ถูกต้อง
    df["cost_per_person"] = df["cost_per_person"].astype(float)
    df["suggested_days"] = df["suggested_days"].astype(float)
    df["review_score"] = df["review_score"].astype(float)
    df["interest_tags"] = df["interest_tags"].fillna("")

    # คอลัมน์ image_url เป็นทางเลือก (ผู้ใช้กรอกลิงก์รูปเองทีหลังได้) ถ้ายังไม่มีคอลัมน์นี้เลย ให้เติมค่าว่างไว้ก่อน
    if "image_url" not in df.columns:
        df["image_url"] = ""
    df["image_url"] = df["image_url"].fillna("")

    return df.reset_index(drop=True)


# ----------------------------------------------------------------------
# 2) ฟังก์ชันคำนวณคะแนนรายปัจจัย (แต่ละฟังก์ชัน normalize ผลลัพธ์ให้อยู่ในช่วง 0-1)
# ----------------------------------------------------------------------
def calculate_interest_score(place_tags: str, user_interests: list[str]) -> float:
    """
    ปัจจัยความสนใจ: สัดส่วนของความสนใจที่ผู้ใช้เลือก ซึ่งตรงกับ tag ของสถานที่
    เช่น ผู้ใช้เลือก 3 อย่าง ตรงกับสถานที่ 2 อย่าง -> คะแนน = 2/3
    """
    if not user_interests:
        return 0.5  # ผู้ใช้ไม่ระบุความสนใจ ให้คะแนนกลางๆ ทุกสถานที่เท่ากัน

    place_tag_list = [t.strip() for t in place_tags.split(",") if t.strip()]
    if not place_tag_list:
        return 0.0

    matched = len(set(user_interests) & set(place_tag_list))
    return matched / len(user_interests)


def calculate_budget_score(cost: float, user_budget: float) -> float:
    """
    ปัจจัยงบประมาณ: สถานที่ที่อยู่ในงบประมาณผู้ใช้ได้คะแนนเต็ม 1.0
    ยิ่งเกินงบประมาณมาก คะแนนยิ่งลดลง (จนต่ำสุด 0)
    """
    if user_budget <= 0:
        return 0.0
    if cost <= user_budget:
        return 1.0
    over_ratio = (cost - user_budget) / user_budget
    return max(0.0, 1.0 - over_ratio)


def calculate_duration_score(suggested_days: float, user_days: float) -> float:
    """
    ปัจจัยระยะเวลา: ยิ่งจำนวนวันที่แนะนำใกล้เคียงกับเวลาที่ผู้ใช้มี คะแนนยิ่งสูง
    """
    if user_days <= 0:
        return 0.0
    diff = abs(suggested_days - user_days)
    denom = max(suggested_days, user_days)
    return max(0.0, 1.0 - diff / denom)


def calculate_review_score(review_score: float) -> float:
    """
    คะแนนรีวิว: normalize คะแนนรีวิว (เต็ม 5) ให้อยู่ในช่วง 0-1
    """
    return max(0.0, min(1.0, review_score / 5.0))


# ----------------------------------------------------------------------
# 3) Weighted Scoring (บทที่ 3.5 การคำนวณคะแนน) -> calculate_score()
# ----------------------------------------------------------------------
def calculate_score(row: pd.Series, user_budget: float, user_days: float,
                     user_interests: list[str]) -> pd.Series:
    interest_s = calculate_interest_score(row["interest_tags"], user_interests)
    budget_s = calculate_budget_score(row["cost_per_person"], user_budget)
    duration_s = calculate_duration_score(row["suggested_days"], user_days)
    review_s = calculate_review_score(row["review_score"])

    total_score = (
        WEIGHT_INTEREST * interest_s
        + WEIGHT_BUDGET * budget_s
        + WEIGHT_DURATION * duration_s
        + WEIGHT_REVIEW * review_s
    ) * 100  # แปลงเป็นคะแนนเต็ม 100 เพื่อให้แสดงผลเข้าใจง่าย #
    #คะแนนรวม = (ความสนใจ × 40%) + (งบประมาณ × 30%) + (ระยะเวลา × 20%) + (รีวิว × 10%)


    return pd.Series({
        "interest_score": round(interest_s * 100, 1),
        "budget_score": round(budget_s * 100, 1),
        "duration_score": round(duration_s * 100, 1),
        "review_score_norm": round(review_s * 100, 1),
        "total_score": round(total_score, 1),
    })


def filter_by_province(df: pd.DataFrame, user_provinces: list[str]) -> pd.DataFrame:
    """
    ตัวกรองจังหวัด: ถ้าผู้ใช้ไม่เลือกจังหวัดใดเลย ให้แสดงทุกจังหวัด (ไม่กรอง)
    ถ้าเลือกไว้ ให้แสดงเฉพาะสถานที่ที่อยู่ในจังหวัดที่เลือกเท่านั้น
    """
    if not user_provinces:
        return df
    return df[df["province"].isin(user_provinces)].reset_index(drop=True)


def recommend(df: pd.DataFrame, user_budget: float, user_days: float,
               user_interests: list[str], top_n: int = TOP_N) -> pd.DataFrame:
    """
    คำนวณคะแนนของทุกแถว แล้วจัดอันดับ (Ranking) ด้วย sort_values()
    คืนค่าเฉพาะ Top N อันดับแรก -> ระบบแนะนำ Top 5
    """
    if df.empty:
        return df

    scored = df.join(
        df.apply(lambda row: calculate_score(row, user_budget, user_days, user_interests), axis=1)
    )

    # Ranking: เรียงจากคะแนนรวมมากไปน้อย
    ranked = scored.sort_values(by="total_score", ascending=False).reset_index(drop=True)

    return ranked.head(top_n)


# ----------------------------------------------------------------------
# 4) ส่วนติดต่อผู้ใช้ (Streamlit UI) — บทที่ 3.6 การออกแบบหน้าจอ
# ----------------------------------------------------------------------
def main():
    st.set_page_config(page_title="TravelMatch", page_icon="🧭", layout="wide")

    # Custom background color (main content + sidebar)
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #;
        }
        section[data-testid="stSidebar"] {
            background-color: #;
        }
        section[data-testid="stSidebar"] * {
            color: # !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("🧭 TravelMatch")

    if BANNER_IMAGE_URL:
        st.image(BANNER_IMAGE_URL, use_container_width=True)

    st.caption("ระบบแนะนำสถานที่ท่องเที่ยวที่เหมาะสมกับงบประมาณ ระยะเวลา และความสนใจของผู้ใช้")

    df = load_data()

    # รวบรวม tag ความสนใจทั้งหมดจากชุดข้อมูล เพื่อให้ผู้ใช้เลือก
    all_tags = sorted({
        tag.strip()
        for tags in df["interest_tags"]
        for tag in tags.split(",")
        if tag.strip()
    })

    # รวบรวมรายชื่อจังหวัดทั้งหมดจากชุดข้อมูล เพื่อให้ผู้ใช้เลือกกรอง
    all_provinces = sorted(df["province"].unique().tolist())

    # ---------------- Sidebar: รับข้อมูลความต้องการของผู้ใช้ (User Data) ----------------
    with st.sidebar:
        st.header("📝 บอกความต้องการของคุณ")

        user_provinces = st.multiselect(
            "📍 จังหวัด (ไม่เลือก = แสดงทุกจังหวัด)",
            options=all_provinces,
            default=[],
        )
        user_budget = st.number_input(
            "งบประมาณต่อคน (บาท)", min_value=500, max_value=20000, value=3000, step=100
        )
        user_days = st.number_input(
            "ระยะเวลาที่มี (วัน)", min_value=1, max_value=10, value=2, step=1
        )
        user_people = st.number_input(
            "👥 จำนวนคน (ผู้ร่วมเดินทาง)", min_value=1, max_value=20, value=2, step=1
        )
        user_interests = st.multiselect(
            "ความสนใจ (เลือกได้หลายข้อ)",
            options=all_tags,
            default=["ธรรมชาติ", "ผ่อนคลาย"] if {"ธรรมชาติ", "ผ่อนคลาย"} <= set(all_tags) else [],
        )

        st.divider()
        run_button = st.button("🔍 ค้นหาสถานที่ที่ใช่สำหรับคุณ", use_container_width=True, type="primary")

        with st.expander("⚙️ น้ำหนักปัจจัยที่ระบบใช้คำนวณ"):
            st.write(f"- ความสนใจ: **{WEIGHT_INTEREST*100:.0f}%**")
            st.write(f"- งบประมาณ: **{WEIGHT_BUDGET*100:.0f}%**")
            st.write(f"- ระยะเวลา: **{WEIGHT_DURATION*100:.0f}%**")
            st.write(f"- คะแนนรีวิว: **{WEIGHT_REVIEW*100:.0f}%**")

    # ---------------- ผลลัพธ์ ----------------
    if run_button or "last_result" in st.session_state:
        if run_button:
            filtered_df = filter_by_province(df, user_provinces)
            st.session_state["last_result"] = recommend(filtered_df, user_budget, user_days, user_interests)
            st.session_state["last_provinces"] = user_provinces
            st.session_state["last_people"] = user_people

        result = st.session_state["last_result"]

        if result.empty:
            st.warning(
                f"ไม่พบสถานที่ท่องเที่ยวในจังหวัดที่เลือก ({', '.join(st.session_state['last_provinces'])}) "
                "ลองเลือกจังหวัดอื่น หรือไม่เลือกจังหวัดเลยเพื่อดูทุกที่"
            )
            return

        province_label = (
            f" ในจังหวัด {', '.join(st.session_state['last_provinces'])}"
            if st.session_state.get("last_provinces") else ""
        )
        st.subheader(f"🏆 Top {len(result)} สถานที่แนะนำสำหรับคุณ{province_label}")

        for i, row in result.iterrows():
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"### {i+1}. {row['place_name']} — {row['province']}")
                    if row.get("image_url"):
                        st.image(row["image_url"], use_container_width=True)
                    st.write(row["description"])
                    st.caption(f"หมวดหมู่: {row['category']} | tag: {row['interest_tags']}")
                    people = st.session_state.get("last_people", 1)
                    total_cost = row["cost_per_person"] * people
                    st.write(
                        f"💰 ค่าใช้จ่ายโดยประมาณ: {row['cost_per_person']:,.0f} บาท/คน  |  "
                        f"👥 {people} คน รวม **{total_cost:,.0f} บาท**  |  "
                        f"🗓️ ระยะเวลาแนะนำ: {row['suggested_days']:.0f} วัน  |  "
                        f"⭐ รีวิว: {row['review_score']:.1f}/5"
                    )
                with col2:
                    st.metric("คะแนนความเหมาะสม", f"{row['total_score']:.1f}")
                    st.progress(min(1.0, row["total_score"] / 100))

                with st.expander("ดูรายละเอียดคะแนนแต่ละปัจจัย (Weighted Scoring)"):
                    score_detail = pd.DataFrame({
                        "ปัจจัย": ["ความสนใจ (40%)", "งบประมาณ (30%)", "ระยะเวลา (20%)", "คะแนนรีวิว (10%)"],
                        "คะแนน (เต็ม 100)": [
                            row["interest_score"], row["budget_score"],
                            row["duration_score"], row["review_score_norm"],
                        ],
                    })
                    st.dataframe(score_detail, hide_index=True, use_container_width=True)

        with st.expander("📊 ดูตารางคะแนนทั้งหมด (สำหรับอ้างอิงในบทที่ 4)"):
            people = st.session_state.get("last_people", 1)
            table = result.copy()
            table["total_cost_group"] = table["cost_per_person"] * people
            st.dataframe(
                table[[
                    "place_id", "place_name", "province", "category",
                    "cost_per_person", "total_cost_group",
                    "interest_score", "budget_score", "duration_score",
                    "review_score_norm", "total_score",
                ]],
                hide_index=True, use_container_width=True,
            )
    else:
        st.info("⬅️ กรอกงบประมาณ ระยะเวลา และความสนใจในแถบด้านซ้าย แล้วกดปุ่ม 'ค้นหาสถานที่ที่ใช่สำหรับคุณ'")
        st.dataframe(df.drop(columns=["interest_tags"]), hide_index=True, use_container_width=True)


if __name__ == "__main__":
    main()
