# -*- coding: utf-8 -*-
"""
TravelMatch 🧭 (Realtime Edition — ตรงตามรายงานบทที่ 3-4)

ระบบแนะนำสถานที่ท่องเที่ยวที่เหมาะสมกับงบประมาณ ระยะเวลา และความสนใจของผู้ใช้
ดึงข้อมูลสถานที่จริงแบบเรียลไทม์จาก OpenStreetMap (Overpass API) แทนไฟล์ CSV คงที่

โครงสร้างอ้างอิงจากรายงาน:
- 3.3 ข้อมูลที่ใช้ในระบบ (ข้อมูลผู้ใช้ / ข้อมูลสถานที่ท่องเที่ยว)
- 3.5 การคำนวณคะแนน (Weighted Scoring: ความสนใจ 40% / งบประมาณ 30% / ระยะเวลา 20% / รีวิว 10%)
- 3.6 การออกแบบหน้าจอ (4 หน้าจอ: หน้าแรก / กรอกข้อมูล / ผลการแนะนำ / รายละเอียด)

หมายเหตุสำคัญ: ปัจจัยที่ "ถ่วงน้ำหนัก" ในการคำนวณคะแนนมีแค่ 4 ปัจจัยตามรายงาน (3.5)
ส่วนข้อมูลอื่น เช่น รูปแบบการเดินทาง / กิจกรรม / ฤดูกาล / จำนวนผู้เดินทาง
ใช้เป็น "ข้อมูลประกอบการตัดสินใจ" และเหตุผลประกอบการแนะนำเท่านั้น ไม่ได้เข้าสูตรคะแนนรวม
เนื่องจาก OSM ไม่มีข้อมูลเหล่านี้ตรงๆ จึงประมาณจากประเภทสถานที่ (ระบุไว้ในคอมเมนต์ทุกจุด)
"""

import math
import requests
import pandas as pd
import streamlit as st

# ----------------------------------------------------------------------------
# ค่าคงที่ / การตั้งค่า
# ----------------------------------------------------------------------------

TOP_N = 5

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "TravelMatchApp/1.0 (educational project)"}

# ประเภทสถานที่ที่สนใจ -> OSM tag (key, value) ที่จะค้นหา
INTEREST_TAG_MAP = {
    "ประวัติศาสตร์ / วัฒนธรรม": [("historic", None), ("tourism", "museum"), ("tourism", "attraction")],
    "ธรรมชาติ": [("natural", None), ("leisure", "park"), ("tourism", "viewpoint")],
    "ทะเล / ชายหาด": [("natural", "beach")],
    "ช้อปปิ้ง / ไลฟ์สไตล์": [("shop", "mall")],
    "วัด / ศาสนสถาน": [("amenity", "place_of_worship")],
    "สวนสนุก / กิจกรรม": [("tourism", "theme_park"), ("leisure", "water_park"), ("tourism", "zoo")],
}

# รูปแบบการเดินทาง (ข้อมูลผู้ใช้ตามรายงาน 3.3) — ใช้เป็นเหตุผลประกอบ ไม่เข้าสูตรคะแนน
TRAVEL_STYLE_OPTIONS = ["พักผ่อน", "ผจญภัย", "ครอบครัว", "ถ่ายภาพ"]

# กิจกรรมที่ต้องการ (ข้อมูลผู้ใช้ตามรายงาน 3.3) — ใช้เป็นเหตุผลประกอบ ไม่เข้าสูตรคะแนน
ACTIVITY_OPTIONS = ["เดินป่า/เดินเล่น", "ถ่ายภาพ", "ปิกนิก", "ช้อปปิ้ง", "ชมวัฒนธรรม", "เล่นน้ำ", "เครื่องเล่น/ผจญภัย"]

# ---- ค่าประมาณตามประเภทสถานที่ (fallback เมื่อ OSM ไม่มีข้อมูลตรงๆ) ----

DEFAULT_COST_BY_TYPE = {
    "museum": 150, "attraction": 100, "viewpoint": 0, "park": 0, "beach": 0,
    "theme_park": 500, "water_park": 400, "zoo": 250, "place_of_worship": 0,
    "mall": 0, "historic": 50, "natural": 0, "default": 100,
}

DEFAULT_DURATION_BY_TYPE = {  # ชั่วโมง
    "museum": 2.0, "attraction": 1.5, "viewpoint": 0.5, "park": 1.5, "beach": 2.5,
    "theme_park": 4.0, "water_park": 3.0, "zoo": 3.0, "place_of_worship": 1.0,
    "mall": 2.0, "historic": 1.0, "natural": 1.5, "default": 1.5,
}

ACTIVITY_BY_TYPE = {
    "museum": ["ชมวัฒนธรรม", "ถ่ายภาพ"], "attraction": ["ถ่ายภาพ"], "viewpoint": ["ถ่ายภาพ", "เดินป่า/เดินเล่น"],
    "park": ["เดินป่า/เดินเล่น", "ปิกนิก"], "beach": ["เล่นน้ำ", "ถ่ายภาพ"],
    "theme_park": ["เครื่องเล่น/ผจญภัย"], "water_park": ["เล่นน้ำ", "เครื่องเล่น/ผจญภัย"],
    "zoo": ["เครื่องเล่น/ผจญภัย", "ถ่ายภาพ"], "place_of_worship": ["ชมวัฒนธรรม"],
    "mall": ["ช้อปปิ้ง"], "historic": ["ชมวัฒนธรรม", "ถ่ายภาพ"], "natural": ["เดินป่า/เดินเล่น", "ถ่ายภาพ"],
    "default": ["ถ่ายภาพ"],
}

SEASON_BY_TYPE = {
    "beach": "หน้าร้อน (พ.ย. - เม.ย.) เหมาะที่สุด", "natural": "หน้าหนาว - หน้าร้อน อากาศเย็นสบาย",
    "park": "ตลอดปี (เลี่ยงช่วงฝนตกหนัก)", "viewpoint": "หน้าหนาวจะเห็นวิวชัดที่สุด",
    "water_park": "หน้าร้อนเหมาะที่สุด", "theme_park": "ตลอดปี", "zoo": "ตลอดปี",
    "default": "ตลอดปี",
}

TRAVEL_STYLE_BY_TYPE = {
    "museum": ["ครอบครัว", "พักผ่อน"], "attraction": ["พักผ่อน", "ถ่ายภาพ"],
    "viewpoint": ["ถ่ายภาพ", "พักผ่อน"], "park": ["พักผ่อน", "ครอบครัว"],
    "beach": ["พักผ่อน", "ถ่ายภาพ"], "theme_park": ["ครอบครัว", "ผจญภัย"],
    "water_park": ["ครอบครัว", "ผจญภัย"], "zoo": ["ครอบครัว"],
    "place_of_worship": ["ครอบครัว", "พักผ่อน"], "mall": ["ครอบครัว", "พักผ่อน"],
    "historic": ["ถ่ายภาพ", "ครอบครัว"], "natural": ["ผจญภัย", "ถ่ายภาพ"],
    "default": ["พักผ่อน"],
}


# ----------------------------------------------------------------------------
# Geocoding: แปลงชื่อจังหวัด/พื้นที่ เป็นพิกัด
# ----------------------------------------------------------------------------

@st.cache_data(ttl=86400, show_spinner=False)
def geocode_location(place_name: str):
    params = {"q": place_name, "format": "json", "limit": 1}
    resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ----------------------------------------------------------------------------
# ส่วนจัดการข้อมูล: ดึงข้อมูลสถานที่ท่องเที่ยวแบบเรียลไทม์จาก Overpass API (แทนไฟล์ CSV)
# ----------------------------------------------------------------------------

def _build_overpass_query(lat, lon, radius_m, tag_pairs):
    clauses = []
    for key, value in tag_pairs:
        if value:
            clauses.append(f'node["{key}"="{value}"](around:{radius_m},{lat},{lon});')
        else:
            clauses.append(f'node["{key}"](around:{radius_m},{lat},{lon});')
    body = "\n".join(clauses)
    return f"[out:json][timeout:25];\n(\n{body}\n);\nout body;"


@st.cache_data(ttl=1800, show_spinner=False)
def load_data(lat: float, lon: float, radius_km: float, selected_interests: list):
    """ส่วนจัดการข้อมูล (3.8 ข้อ 2): ดึงข้อมูลสถานที่ท่องเที่ยวจริงจาก OSM แทนการอ่านไฟล์ CSV"""
    tag_pairs = []
    categories = selected_interests if selected_interests else list(INTEREST_TAG_MAP.keys())
    for cat in categories:
        tag_pairs.extend(INTEREST_TAG_MAP.get(cat, []))
    tag_pairs = list(dict.fromkeys(tag_pairs))

    query = _build_overpass_query(lat, lon, int(radius_km * 1000), tag_pairs)

    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        st.error(f"ดึงข้อมูลจาก OpenStreetMap ไม่สำเร็จ: {e}")
        return pd.DataFrame()

    rows = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue

        place_type = (
            tags.get("tourism") or tags.get("historic") or tags.get("natural")
            or tags.get("leisure") or tags.get("shop") or tags.get("amenity") or "default"
        )

        matched_interests = [
            cat for cat, pairs in INTEREST_TAG_MAP.items()
            if any((k in tags and (v is None or tags.get(k) == v)) for k, v in pairs)
        ]

        province = tags.get("addr:province") or tags.get("addr:city") or tags.get("addr:state") or "ไม่ระบุ"

        fee_tag = tags.get("fee")
        est_cost = 0 if fee_tag == "no" else DEFAULT_COST_BY_TYPE.get(place_type, DEFAULT_COST_BY_TYPE["default"])
        est_duration = DEFAULT_DURATION_BY_TYPE.get(place_type, DEFAULT_DURATION_BY_TYPE["default"])

        # ความนิยม/ความน่าเชื่อถือ: มี wikipedia/wikidata ผูกไว้ ถือว่าเป็นสถานที่ที่มีชื่อเสียง/รีวิวดี
        has_wiki = bool(tags.get("wikipedia") or tags.get("wikidata"))
        credibility = 1.0 if has_wiki else 0.55
        popularity_label = "เป็นที่นิยม" if has_wiki else "ทั่วไป"

        rows.append({
            "name": name,
            "province": province,
            "type": place_type,
            "interests": matched_interests,
            "lat": el.get("lat"),
            "lon": el.get("lon"),
            "estimated_cost": est_cost,
            "estimated_duration_hr": est_duration,
            "credibility_score": credibility,
            "popularity": popularity_label,
            "activities": ACTIVITY_BY_TYPE.get(place_type, ACTIVITY_BY_TYPE["default"]),
            "season": SEASON_BY_TYPE.get(place_type, SEASON_BY_TYPE["default"]),
            "travel_styles": TRAVEL_STYLE_BY_TYPE.get(place_type, TRAVEL_STYLE_BY_TYPE["default"]),
        })

    return pd.DataFrame(rows).drop_duplicates(subset=["name"]).reset_index(drop=True)


# ----------------------------------------------------------------------------
# ส่วนคำนวณคะแนน (3.5 Weighted Scoring: ความสนใจ 40% / งบประมาณ 30% / ระยะเวลา 20% / รีวิว 10%)
# ----------------------------------------------------------------------------

def calculate_interest_score(row, selected_interests):
    if not selected_interests:
        return 1.0
    if not row["interests"]:
        return 0.0
    matched = len(set(row["interests"]) & set(selected_interests))
    return matched / len(selected_interests)


def calculate_budget_score(row, budget_per_person):
    if budget_per_person <= 0:
        return 0.0
    cost = row["estimated_cost"]
    if cost <= budget_per_person:
        return 1.0
    over_ratio = (cost - budget_per_person) / budget_per_person
    return max(0.0, 1.0 - over_ratio)


def calculate_duration_score(row, available_days):
    available_hours = available_days * 8  # สมมติเที่ยวได้วันละ ~8 ชม.
    if available_hours <= 0:
        return 0.0
    duration = row["estimated_duration_hr"]
    if duration <= available_hours:
        return 1.0
    return max(0.0, available_hours / duration)


def calculate_review_score(row):
    return row["credibility_score"]


def calculate_score(row, selected_interests, budget_per_person, available_days):
    interest = calculate_interest_score(row, selected_interests)
    budget = calculate_budget_score(row, budget_per_person)
    duration = calculate_duration_score(row, available_days)
    review = calculate_review_score(row)
    total = (interest * 0.40) + (budget * 0.30) + (duration * 0.20) + (review * 0.10)
    return interest, budget, duration, review, total


def recommend(df, selected_interests, budget_per_person, available_days, top_n=TOP_N):
    if df.empty:
        return df
    df = df.copy()
    scores = df.apply(
        lambda r: calculate_score(r, selected_interests, budget_per_person, available_days),
        axis=1, result_type="expand",
    )
    scores.columns = ["interest_score", "budget_score", "duration_score", "review_score", "total_score"]
    df = pd.concat([df, scores], axis=1)
    return df.sort_values("total_score", ascending=False).head(top_n).reset_index(drop=True)


def build_reasons(row, selected_interests, travel_style):
    """สร้างเหตุผลประกอบการแนะนำ (ใช้แสดงในหน้าผลลัพธ์ ไม่ใช่ตัวเลขที่เข้าสูตรคะแนน)"""
    reasons = []
    if selected_interests and row["interest_score"] >= 0.5:
        reasons.append("ตรงกับความสนใจที่เลือก")
    if row["budget_score"] >= 0.8:
        reasons.append("อยู่ในงบประมาณ")
    if row["duration_score"] >= 0.8:
        reasons.append("เหมาะกับระยะเวลาที่มี")
    if row["review_score"] >= 0.8:
        reasons.append("มีคะแนนรีวิวในระดับดี")
    if travel_style and travel_style in row["travel_styles"]:
        reasons.append(f"เหมาะกับรูปแบบการเดินทางแบบ{travel_style}")
    if not reasons:
        reasons.append("เป็นตัวเลือกที่ใกล้เคียงความต้องการของคุณมากที่สุดในพื้นที่นี้")
    return reasons


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


def screen_form():
    st.title("กรอกข้อมูลความต้องการของคุณ")

    location_text = st.text_input("จังหวัด / พื้นที่ที่ต้องการเที่ยว", value="เชียงใหม่")
    col1, col2 = st.columns(2)
    with col1:
        budget = st.number_input("งบประมาณต่อคน (บาท)", min_value=0, value=1000, step=100)
        days = st.number_input("จำนวนวัน", min_value=1, value=1, step=1)
    with col2:
        travelers = st.number_input("จำนวนผู้เดินทาง (คน)", min_value=1, value=1, step=1)
        travel_style = st.selectbox("รูปแบบการเดินทาง", TRAVEL_STYLE_OPTIONS)

    interests = st.multiselect("ประเภทสถานที่ที่สนใจ", list(INTEREST_TAG_MAP.keys()))
    activities = st.multiselect("กิจกรรมที่ต้องการ (ถ้ามี)", ACTIVITY_OPTIONS)

    with st.expander("ตั้งค่าการค้นหาขั้นสูง"):
        radius_km = st.slider("รัศมีการค้นหารอบพื้นที่ (กม.)", min_value=1, max_value=30, value=10)

    if st.button("🔎 ค้นหาสถานที่ที่เหมาะกับฉัน", type="primary"):
        if not location_text.strip():
            st.warning("กรุณาระบุจังหวัด/พื้นที่ที่ต้องการเที่ยว")
            return

        with st.spinner("กำลังค้นหาพิกัด..."):
            coords = geocode_location(location_text)
        if not coords:
            st.error("ไม่พบพื้นที่ที่ระบุ ลองพิมพ์ชื่อจังหวัด/พื้นที่ใหม่อีกครั้ง")
            return
        lat, lon = coords

        with st.spinner("กำลังดึงข้อมูลสถานที่แบบเรียลไทม์จาก OpenStreetMap..."):
            df = load_data(lat, lon, radius_km, interests)

        if df.empty:
            st.warning("ไม่พบสถานที่ในพื้นที่นี้ ลองขยายรัศมีการค้นหา หรือเปลี่ยนประเภทสถานที่")
            return

        df["distance_km"] = df.apply(lambda r: round(haversine_km(lat, lon, r["lat"], r["lon"]), 1), axis=1)
        results = recommend(df, interests, budget, days)

        st.session_state.results = results
        st.session_state.user_input = {
            "location_text": location_text, "budget": budget, "days": days,
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
        f"พื้นที่: {user_input.get('location_text')} | งบประมาณ/คน: {user_input.get('budget')} บาท | "
        f"จำนวนวัน: {user_input.get('days')} | ผู้เดินทาง: {user_input.get('travelers')} คน | "
        f"รูปแบบ: {user_input.get('travel_style')}"
    )

    # ตารางคะแนนแยกปัจจัย ตามตัวอย่างในรายงาน 4.2
    table = results.copy()
    table.insert(0, "อันดับ", range(1, len(table) + 1))
    table_display = table[[
        "อันดับ", "name", "interest_score", "budget_score", "duration_score", "review_score", "total_score"
    ]].rename(columns={
        "name": "สถานที่", "interest_score": "คะแนนความสนใจ", "budget_score": "คะแนนงบประมาณ",
        "duration_score": "คะแนนระยะเวลา", "review_score": "คะแนนรีวิว", "total_score": "คะแนนรวม",
    })
    for col in ["คะแนนความสนใจ", "คะแนนงบประมาณ", "คะแนนระยะเวลา", "คะแนนรีวิว", "คะแนนรวม"]:
        table_display[col] = (table_display[col] * 100).round(0).astype(int).astype(str) + "%"
    st.dataframe(table_display, hide_index=True, use_container_width=True)

    st.write("---")

    for i, row in results.iterrows():
        with st.container(border=True):
            st.subheader(f"อันดับ {i + 1}: {row['name']}")
            st.write(f"จังหวัด/พื้นที่: {row['province']} | ประเภท: {row['type']} | ระยะทาง: {row['distance_km']} กม.")
            st.write(
                f"ค่าใช้จ่ายโดยประมาณ: {row['estimated_cost']} บาท/คน | "
                f"ระยะเวลาแนะนำ: {row['estimated_duration_hr']} ชม. | ความนิยม: {row['popularity']}"
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

    col1, col2 = st.columns(2)
    with col1:
        st.metric("ค่าใช้จ่ายโดยประมาณ (ต่อคน)", f"{place['estimated_cost']} บาท")
        st.metric("ค่าใช้จ่ายรวมกลุ่มโดยประมาณ", f"{place['estimated_cost'] * travelers} บาท")
        st.metric("ระยะเวลาแนะนำ", f"{place['estimated_duration_hr']} ชม.")
    with col2:
        st.metric("คะแนนรีวิว (ประมาณ)", f"{place['credibility_score'] * 100:.0f}%")
        st.metric("ความนิยม", place["popularity"])
        st.metric("ระยะทางจากจุดค้นหา", f"{place['distance_km']} กม.")

    st.write("**กิจกรรมที่ทำได้:**", ", ".join(place["activities"]))
    st.write("**ฤดูกาลที่เหมาะสม:**", place["season"])
    st.write("**เหมาะกับรูปแบบการเดินทาง:**", ", ".join(place["travel_styles"]))

    if place.get("lat") and place.get("lon"):
        maps_url = f"https://www.google.com/maps?q={place['lat']},{place['lon']}"
        st.write(f"**ข้อมูลการเดินทาง:** [เปิดใน Google Maps]({maps_url})")

    st.caption("หมายเหตุ: ค่าใช้จ่าย/ระยะเวลา/ฤดูกาล/รูปแบบการเดินทาง เป็นค่าประมาณจากประเภทสถานที่ เนื่องจาก OpenStreetMap ไม่มีข้อมูลเหล่านี้ครบทุกแห่ง")

    if st.button("← กลับไปหน้าผลลัพธ์"):
        go_to("results")


def main():
    st.set_page_config(page_title="TravelMatch 🧭", page_icon="🧭")
    if "page" not in st.session_state:
        st.session_state.page = "home"

    page = st.session_state.page
    if page == "home":
        screen_home()
    elif page == "form":
        screen_form()
    elif page == "results":
        screen_results()
    elif page == "detail":
        screen_detail()


if __name__ == "__main__":
    main()
