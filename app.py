# -*- coding: utf-8 -*-
"""
TravelMatch 🧭 (Static / CSV Edition — ตรงตามรายงานบทที่ 3-4, ไม่ใช้ข้อมูลเรียลไทม์)

ระบบแนะนำสถานที่ท่องเที่ยวที่เหมาะสมกับงบประมาณ ระยะเวลา และความสนใจของผู้ใช้
อ่านข้อมูลสถานที่จาก travel_data.csv (สร้างโดย generate_data.py) ตามเครื่องมือที่ระบุใน 3.7
(Python, Pandas, NumPy, Streamlit, CSV) — ไม่มีการเชื่อมต่ออินเทอร์เน็ต/API ภายนอกใดๆ

โครงสร้างอ้างอิงจากรายงาน:
- 3.3 ข้อมูลที่ใช้ในระบบ (ข้อมูลผู้ใช้ / ข้อมูลสถานที่ท่องเที่ยว)
- 3.5 การคำนวณคะแนน (Weighted Scoring: ความสนใจ 40% / งบประมาณ 30% / ระยะเวลา 20% / รีวิว 10%)
- 3.6 การออกแบบหน้าจอ (4 หน้าจอ: หน้าแรก / กรอกข้อมูล / ผลการแนะนำ / รายละเอียด)

หมายเหตุ: รูปแบบการเดินทาง / กิจกรรม / ฤดูกาล / จำนวนผู้เดินทาง เป็น "ข้อมูลประกอบการตัดสินใจ"
และใช้สร้างเหตุผลประกอบการแนะนำเท่านั้น ไม่ได้เข้าสูตรคะแนนรวม (มีแค่ 4 ปัจจัยถ่วงน้ำหนักตาม 3.5)
"""

import pandas as pd
import streamlit as st

TOP_N = 5
DATA_FILE = "travel_data.csv"

INTEREST_OPTIONS = [
    "ธรรมชาติ", "ทะเล / ชายหาด", "ประวัติศาสตร์ / วัฒนธรรม",
    "วัด / ศาสนสถาน", "ช้อปปิ้ง / ไลฟ์สไตล์", "สวนสนุก / กิจกรรม",
]
TRAVEL_STYLE_OPTIONS = ["พักผ่อน", "ผจญภัย", "ครอบครัว", "ถ่ายภาพ"]
ACTIVITY_OPTIONS = [
    "เดินป่า/เดินเล่น", "ถ่ายภาพ", "ปิกนิก", "เล่นน้ำ", "พักผ่อน",
    "ชมวัฒนธรรม", "ไหว้พระ", "ช้อปปิ้ง", "เครื่องเล่น/ผจญภัย",
]

TYPE_ICON = {
    "ธรรมชาติ": "🌳", "ทะเล / ชายหาด": "🏖️", "ประวัติศาสตร์ / วัฒนธรรม": "🏛️",
    "วัด / ศาสนสถาน": "🛕", "ช้อปปิ้ง / ไลฟ์สไตล์": "🛍️", "สวนสนุก / กิจกรรม": "🎢",
    "default": "📷",
}


# ----------------------------------------------------------------------------
# ส่วนจัดการข้อมูล (3.8 ข้อ 2): นำข้อมูลสถานที่ท่องเที่ยวจากไฟล์ CSV เข้าสู่ระบบ
# ----------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_data():
    df = pd.read_csv(DATA_FILE)
    # ตรวจสอบความถูกต้องของข้อมูลก่อนนำไปประมวลผล (ตาม 3.8 ข้อ 2)
    required_cols = [
        "name", "province", "type", "cost", "duration_days", "review_score",
        "distance_km", "popularity", "activities", "season", "travel_style",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"ไฟล์ข้อมูลขาดคอลัมน์: {', '.join(missing)}")
        return pd.DataFrame()

    df = df.dropna(subset=["name", "cost", "duration_days", "review_score"])
    df["activities"] = df["activities"].apply(lambda s: [a.strip() for a in str(s).split(",")])
    df["travel_style"] = df["travel_style"].apply(lambda s: [a.strip() for a in str(s).split(",")])
    return df


# ----------------------------------------------------------------------------
# ส่วนคำนวณคะแนน (3.5 Weighted Scoring: ความสนใจ 40% / งบประมาณ 30% / ระยะเวลา 20% / รีวิว 10%)
# ----------------------------------------------------------------------------

def calculate_interest_score(row, selected_interests):
    if not selected_interests:
        return 1.0
    return 1.0 if row["type"] in selected_interests else 0.0


def calculate_budget_score(row, budget_per_person):
    if budget_per_person <= 0:
        return 0.0
    cost = row["cost"]
    if cost <= budget_per_person:
        return 1.0
    over_ratio = (cost - budget_per_person) / budget_per_person
    return max(0.0, 1.0 - over_ratio)


def calculate_duration_score(row, available_days):
    if available_days <= 0:
        return 0.0
    d = row["duration_days"]
    if d <= available_days:
        return 1.0
    return max(0.0, available_days / d)


def calculate_review_score(row):
    return row["review_score"] / 100


def calculate_score(row, selected_interests, budget_per_person, available_days):
    interest = calculate_interest_score(row, selected_interests)
    budget = calculate_budget_score(row, budget_per_person)
    duration = calculate_duration_score(row, available_days)
    review = calculate_review_score(row)
    total = (interest * 0.40) + (budget * 0.30) + (duration * 0.20) + (review * 0.10)
    return interest, budget, duration, review, total


def recommend(df, selected_interests, budget_per_person, available_days, province_filter, top_n=TOP_N):
    df = df.copy()
    if province_filter and province_filter != "ทั้งหมด":
        df = df[df["province"] == province_filter]
    if df.empty:
        return df
    scores = df.apply(
        lambda r: calculate_score(r, selected_interests, budget_per_person, available_days),
        axis=1, result_type="expand",
    )
    scores.columns = ["interest_score", "budget_score", "duration_score", "review_score_norm", "total_score"]
    df = pd.concat([df, scores], axis=1)
    return df.sort_values("total_score", ascending=False).head(top_n).reset_index(drop=True)


def build_reasons(row, selected_interests, travel_style):
    reasons = []
    if selected_interests and row["interest_score"] >= 0.99:
        reasons.append("ตรงกับความสนใจที่เลือก")
    if row["budget_score"] >= 0.8:
        reasons.append("อยู่ในงบประมาณ")
    if row["duration_score"] >= 0.8:
        reasons.append("เหมาะกับระยะเวลาที่มี")
    if row["review_score_norm"] >= 0.8:
        reasons.append("มีคะแนนรีวิวในระดับดี")
    if travel_style and travel_style in row["travel_style"]:
        reasons.append(f"เหมาะกับรูปแบบการเดินทางแบบ{travel_style}")
    if not reasons:
        reasons.append("เป็นตัวเลือกที่ใกล้เคียงความต้องการของคุณมากที่สุด")
    return reasons


def format_duration(days: float) -> str:
    if days <= 1:
        return "ทริปวันเดียว"
    nights = int(round(days)) - 1
    return f"{int(round(days))} วัน {nights} คืน"


# ----------------------------------------------------------------------------
# ส่วนติดต่อผู้ใช้ — 4 หน้าจอตามรายงาน 3.6
# ----------------------------------------------------------------------------

def go_to(page):
    st.session_state.page = page


def screen_home():
    st.title("TravelMatch 🧭")
    st.markdown("#### “ค้นหาที่เที่ยวที่ใช่ ให้เหมาะกับงบ เวลา และความสนใจของคุณ”")
    st.write("")
    if st.button("🔍 เริ่มค้นหาสถานที่ท่องเที่ยว", type="primary"):
        go_to("form")


def screen_form(df):
    st.title("กรอกข้อมูลความต้องการของคุณ")

    provinces = ["ทั้งหมด"] + sorted(df["province"].unique().tolist())
    province_filter = st.selectbox("จังหวัด / พื้นที่ที่ต้องการเที่ยว", provinces)

    col1, col2 = st.columns(2)
    with col1:
        budget = st.number_input("งบประมาณต่อคน (บาท)", min_value=0, value=1000, step=100)
        days = st.number_input("จำนวนวัน", min_value=1, value=1, step=1)
    with col2:
        travelers = st.number_input("จำนวนผู้เดินทาง (คน)", min_value=1, value=1, step=1)
        travel_style = st.selectbox("รูปแบบการเดินทาง", TRAVEL_STYLE_OPTIONS)

    interests = st.multiselect("ประเภทสถานที่ที่สนใจ", INTEREST_OPTIONS)
    activities = st.multiselect("กิจกรรมที่ต้องการ (ถ้ามี)", ACTIVITY_OPTIONS)

    if st.button("🔎 ค้นหาสถานที่ที่เหมาะกับฉัน", type="primary"):
        results = recommend(df, interests, budget, days, province_filter)

        if results.empty:
            st.warning("ไม่พบสถานที่ที่ตรงกับเงื่อนไข ลองเปลี่ยนจังหวัด/ประเภทสถานที่")
            return

        st.session_state.results = results
        st.session_state.user_input = {
            "province_filter": province_filter, "budget": budget, "days": days,
            "travelers": travelers, "travel_style": travel_style,
            "interests": interests, "activities": activities,
        }
        go_to("results")

    if st.button("← กลับหน้าแรก"):
        go_to("home")


def screen_results():
    st.title("ผลการแนะนำสถานที่ท่องเที่ยว")
    results = st.session_state.get("results")
    user_input = st.session_state.get("user_input", {})

    if results is None or results.empty:
        st.info("ยังไม่มีผลการค้นหา กรุณากรอกข้อมูลก่อน")
        if st.button("← กลับไปกรอกข้อมูล"):
            go_to("form")
        return

    st.caption(
        f"พื้นที่: {user_input.get('province_filter')} | งบประมาณ/คน: {user_input.get('budget')} บาท | "
        f"จำนวนวัน: {user_input.get('days')} | ผู้เดินทาง: {user_input.get('travelers')} คน | "
        f"รูปแบบ: {user_input.get('travel_style')}"
    )

    # ตารางคะแนนแยกปัจจัย ตามตัวอย่างในรายงาน 4.2
    table = results.copy()
    table.insert(0, "อันดับ", range(1, len(table) + 1))
    table_display = table[[
        "อันดับ", "name", "interest_score", "budget_score", "duration_score", "review_score_norm", "total_score"
    ]].rename(columns={
        "name": "สถานที่", "interest_score": "คะแนนความสนใจ", "budget_score": "คะแนนงบประมาณ",
        "duration_score": "คะแนนระยะเวลา", "review_score_norm": "คะแนนรีวิว", "total_score": "คะแนนรวม",
    })
    for col in ["คะแนนความสนใจ", "คะแนนงบประมาณ", "คะแนนระยะเวลา", "คะแนนรีวิว", "คะแนนรวม"]:
        table_display[col] = (table_display[col] * 100).round(0).astype(int).astype(str) + "%"
    st.dataframe(table_display, hide_index=True, use_container_width=True)

    st.write("---")

    for i, row in results.iterrows():
        with st.container(border=True):
            img_col, info_col = st.columns([1, 3])
            with img_col:
                icon = TYPE_ICON.get(row["type"], TYPE_ICON["default"])
                st.markdown(
                    f"<div style='font-size:64px;text-align:center;padding:20px 0;'>{icon}</div>",
                    unsafe_allow_html=True,
                )
            with info_col:
                st.subheader(f"อันดับ {i + 1}: {row['name']}")
                st.write(f"จังหวัด: {row['province']} | ประเภท: {row['type']} | ระยะทาง: {row['distance_km']} กม.")
                st.write(
                    f"ค่าใช้จ่ายโดยประมาณ: {row['cost']} บาท/คน | "
                    f"ระยะเวลาแนะนำ: {format_duration(row['duration_days'])} | "
                    f"คะแนนความนิยม: {row['popularity']}/100"
                )
                reasons = build_reasons(row, user_input.get("interests", []), user_input.get("travel_style"))
                st.write("เหตุผลที่แนะนำ:")
                for r in reasons:
                    st.write(f"- {r}")
                if st.button("ดูรายละเอียด", key=f"detail_{i}"):
                    st.session_state.selected_place = row.to_dict()
                    go_to("detail")

    st.write("")
    if st.button("← กลับไปแก้ไขข้อมูล"):
        go_to("form")


def screen_detail():
    place = st.session_state.get("selected_place")
    if not place:
        st.info("ยังไม่ได้เลือกสถานที่")
        if st.button("← กลับไปหน้าผลลัพธ์"):
            go_to("results")
        return

    user_input = st.session_state.get("user_input", {})
    travelers = user_input.get("travelers", 1)

    st.title(place["name"])
    st.caption(f"{place['province']} • ประเภท: {place['type']}")

    icon = TYPE_ICON.get(place["type"], TYPE_ICON["default"])
    st.markdown(
        f"<div style='font-size:120px;text-align:center;padding:30px 0;background:#f0f2f6;"
        f"border-radius:12px;'>{icon}</div>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.metric("ค่าใช้จ่ายโดยประมาณ (ต่อคน)", f"{place['cost']} บาท")
        st.metric("ค่าใช้จ่ายรวมกลุ่มโดยประมาณ", f"{place['cost'] * travelers} บาท")
        st.metric("ระยะเวลาแนะนำ", format_duration(place["duration_days"]))
    with col2:
        st.metric("คะแนนรีวิว", f"{place['review_score']}/100")
        st.metric("ความนิยม", f"{place['popularity']}/100")
        st.metric("ระยะทางจากตัวเมือง", f"{place['distance_km']} กม.")

    st.write("**กิจกรรมที่ทำได้:**", ", ".join(place["activities"]))
    st.write("**ฤดูกาลที่เหมาะสม:**", place["season"])
    st.write("**เหมาะกับรูปแบบการเดินทาง:**", ", ".join(place["travel_style"]))

    search_url = f"https://www.google.com/search?q={place['name']} {place['province']}"
    st.write(f"**ข้อมูลการเดินทาง:** [ค้นหาข้อมูลเพิ่มเติม]({search_url})")

    st.caption(
        "หมายเหตุ: ข้อมูลค่าใช้จ่าย/คะแนนรีวิว/ความนิยม เป็นข้อมูลตัวอย่างที่จำลองขึ้นสำหรับต้นแบบระบบ "
        "(ไม่ใช่ข้อมูลจริงจากผู้ให้บริการหรือรีวิวจริง) — ดูข้อจำกัดของระบบในบทที่ 4.5"
    )

    if st.button("← กลับไปหน้าผลลัพธ์"):
        go_to("results")


def main():
    st.set_page_config(page_title="TravelMatch 🧭", page_icon="🧭")
    if "page" not in st.session_state:
        st.session_state.page = "home"

    df = load_data()
    if df.empty:
        st.stop()

    page = st.session_state.page
    if page == "home":
        screen_home()
    elif page == "form":
        screen_form(df)
    elif page == "results":
        screen_results()
    elif page == "detail":
        screen_detail()


if __name__ == "__main__":
    main()
