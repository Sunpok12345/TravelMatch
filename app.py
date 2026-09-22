# -*- coding: utf-8 -*-
"""
TravelMatch 🧭 (Static / CSV Edition — ตรงตามรายงานบทที่ 3-4, ไม่ใช้ข้อมูลเรียลไทม์)

ระบบแนะนำสถานที่ท่องเที่ยวที่เหมาะสมกับงบประมาณ ระยะเวลา และความสนใจของผู้ใช้
อ่านข้อมูลสถานที่จาก travel_data.csv (สร้างโดย generate_data.py) ตามเครื่องมือที่ระบุใน 3.7
(Python, Pandas, NumPy, Streamlit, CSV)

โครงสร้างอ้างอิงจากรายงาน:
- 3.3 ข้อมูลที่ใช้ในระบบ (ข้อมูลผู้ใช้ / ข้อมูลสถานที่ท่องเที่ยว)
- 3.5 การคำนวณคะแนน (Weighted Scoring: ความสนใจ 40% / งบประมาณ 30% / ระยะเวลา 20% / รีวิว 10%)
- 3.6 การออกแบบหน้าจอ (4 หน้าจอ: หน้าแรก / กรอกข้อมูล / ผลการแนะนำ / รายละเอียด)

หมายเหตุ: รูปแบบการเดินทาง / กิจกรรม / ฤดูกาล / จำนวนผู้เดินทาง เป็น "ข้อมูลประกอบการตัดสินใจ"
และใช้สร้างเหตุผลประกอบการแนะนำเท่านั้น ไม่ได้เข้าสูตรคะแนนรวม (มีแค่ 4 ปัจจัยถ่วงน้ำหนักตาม 3.5)

หมายเหตุเรื่องรูปภาพ: ระบบพยายามดึงรูปจริงของสถานที่จาก Wikipedia / Wikimedia Commons ก่อน
(ค้นหาด้วย "ชื่อสถานที่ + จังหวัด" เพื่อลดโอกาสจับคู่ผิด) และใช้ Openverse API เป็น fallback
ขั้นสุดท้าย (คลังรูปลิขสิทธิ์เสรีที่รวมจาก Flickr, Europeana ฯลฯ ไม่ต้องใช้ API key)
เนื่องจากเป็นบริการภายนอก ผลลัพธ์อาจไม่แม่นยำ 100% ในบางสถานที่ที่เล็ก/ไม่มีบทความ
หากต้องการรูปที่แม่นยำแน่นอน ให้ใส่คอลัมน์ image_url ใน travel_data.csv สำหรับสถานที่นั้นๆ
แล้วระบบจะใช้ลิงก์นั้นโดยตรงแทนการค้นหาออนไลน์
"""

from io import BytesIO
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

TOP_N = 5
DATA_FILE_CANDIDATES = [
    "travel_data_final.csv",
    "data/travel_data_final.csv",
    "travel_data_with_images.csv",
    "data/travel_data_with_images.csv",
    "travel_data.csv",
    "data/travel_data.csv",
]

def get_data_file():
    for path in DATA_FILE_CANDIDATES:
        if Path(path).exists():
            return path
    return "travel_data.csv"

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

# สีพื้นหลังพาสเทลของไอคอน (ใช้ตอนไม่พบรูปภาพจริง) — โทนสว่างแต่ไม่จ้า
TYPE_COLOR = {
    "ธรรมชาติ": "#E3F3E1", "ทะเล / ชายหาด": "#DCF0F7", "ประวัติศาสตร์ / วัฒนธรรม": "#F5E9DA",
    "วัด / ศาสนสถาน": "#FBEADF", "ช้อปปิ้ง / ไลฟ์สไตล์": "#F3E4F5", "สวนสนุก / กิจกรรม": "#FFF3D6",
    "default": "#F0F2F6",
}

WIKI_HEADERS = {"User-Agent": "TravelMatchApp/1.0 (educational project; contact: n/a)"}
WIKI_LANGS = ["th", "en"]
OPENVERSE_HEADERS = {"User-Agent": "TravelMatchApp/1.0 (educational project; contact: n/a)"}

# ลิงก์รูปที่ตรวจสอบ/กำหนดเองสำหรับสถานที่สำคัญ
MANUAL_IMAGE_OVERRIDES = {'อุทยานแห่งชาติเขาสก': 'https://mpics-cdn-acc.mgronline.com/pics/Images/563000010828201.JPEG', 'น้ำตกหงาว': 'https://ak-d.tripcdn.com/images/1mi5f2224trjs7e4hBB6A_W_200_0_R5_Q50.jpg?proc=source%2Ftrip', 'เขาหลัก': 'https://cdn.sanity.io/images/nxpteyfv/goguides/0d52b27b06e855cb044e18a56ed507182fb491b3-1600x1066.jpg?auto=format&fit=max&fp-x=0.5&fp-y=0.5&w=100', 'ป่าพรุโต๊ะแดง': 'https://www.puyok.go.th/images/CHATCHAI/TT/pu3.JPEG', 'เขาพนมเบญจา': 'https://th.readme.me/f/39722/cover.jpg', 'อุทยานแห่งชาติแหลมสน': 'https://cbtthailand.dasta.or.th/upload-file-api/Resources/RelateAttraction/Images/RAT850088/1.jpeg', 'เกาะพีพี': 'https://aws-tiqets-cdn.imgix.net/images/content/1f9dead84fe44cd68db2647cb0d4be56.jpeg', 'หาดป่าตอง': '', 'อ่าวนาง': 'https://www.weseektravel.com/wp-content/uploads/2023/06/where-to-stay-ao-nang-1.jpg', 'หาดไร่เลย์': 'https://cdn.audleytravel.com/1600/1144/60/16017015-railay-beach-krabi.jpg', 'เกาะหลีเป๊ะ': '', 'เกาะสมุย': 'https://cdn.sanity.io/images/nxpteyfv/goguides/1cce7443a016225121e8412f64fe678d919426fc-1600x1067.jpg', 'เกาะพะงัน': 'https://cdn.wochenblitz.com/2026/06/koh-phangan-expats-fordern-aus-fuer-thai-zeremonien-featured.jpg', 'หาดนราทัศน์': '', 'เกาะยาวน้อย': 'https://content.r9cdn.net/rimg/dimg/08/e7/5b520c3d-city-58036-1696ddd3567.jpg?crop=true&height=768&width=1366&xhint=2249&yhint=1452', 'หาดคึกคัก': 'https://f.ptcdn.info/873/016/000/1395204530-2377JPG-o.jpg', 'ย่านเมืองเก่าภูเก็ต': 'https://i0.wp.com/thailandgaho.com/wp-content/uploads/2020/04/08_DSC02050.jpg?resize=940%2C627&ssl=1', 'พิพิธภัณฑสถานแห่งชาตินครศรีธรรมราช': 'https://paiteawgun.com/blog/wp-content/uploads/2013/10/%E0%B8%9E%E0%B8%B4%E0%B8%9E%E0%B8%B4%E0%B8%98%E0%B8%A0%E0%B8%B1%E0%B8%93%E0%B8%91%E0%B8%AA%E0%B8%96%E0%B8%B2%E0%B8%99%E0%B9%81%E0%B8%AB%E0%B9%88%E0%B8%87%E0%B8%8A%E0%B8%B2%E0%B8%95%E0%B8%B4%E0%B8%34010.jpg', 'ย่านเมืองเก่าสงขลา': 'https://i.pinimg.com/originals/14/1f/95/141f955f6ae9c8dd18f2c099a152bea5.jpg', 'ป้อมปืนใหญ่ภูเก็ต': '', 'วัดพระมหาธาตุวรมหาวิหาร': 'https://img.wongnai.com/p/1920x0/2019/05/26/4a6a314b98004f10ac28b366eaaccdb3.jpg', 'วัดฉลอง': 'https://www.holidify.com/images/cmsuploads/compressed/Phuket_Thailand_Wat-Chalong-02_20190916180534.jpg', 'วัดถ้ำเสือ': 'https://cdn.prod.rexby.com/image/6c0f40b4fbb944159beedd4300c3152b?format=webp&height=1350&width=1080', 'พระใหญ่ภูเก็ต (บิ๊กพุทธ)': 'https://i0.wp.com/content.phuket101.net/wp-content/uploads/20200530214142/big-buddha-2019.jpg?ssl=1', 'มัสยิดกลางประจำจังหวัดปัตตานี': 'https://news.muslimthaipost.com/uploads/2019/11/06/img/img_157302201322.jpg', 'มัสยิดกลางสงขลา': 'https://f.tpkcdn.com/review-source/54135e08-9eab-46b1-2ef8-579617b3621d.jpg', 'เซ็นทรัล ภูเก็ต ฟลอเรสต้า': 'https://getoccupi.com/cdn-cgi/image/width%3D1200%2Cquality%3D85%2Cformat%3Dauto/https%3A/static.getoccupi.com/uploads/mall_photo/photo/12747/662bcecd47815fd979c94d4e87a165a590a4e413-1600x1066.jpg', 'ตลาดใหญ่หาดใหญ่': 'https://dynamic-media-cdn.tripadvisor.com/media/photo-o/16/d7/5b/d3/kim-yong-market.jpg?h=400&s=1&w=700', 'ถนนคนเดินภูเก็ต (ตลาดหลาดใหญ่)': 'https://i0.wp.com/thailandgaho.com/wp-content/uploads/2020/04/08_DSC02050.jpg?resize=940%2C627&ssl=1', 'เซ็นทรัล เฟสติวัล หาดใหญ่': 'https://ak-d.tripcdn.com/images/1mi3w224x90udo3d5B41B.jpg?proc=source%2Ftrip', 'ภูเก็ตแฟนตาซี': 'https://bluegaxy.com/image/cache/catalog/Show/dzvcxbrsefhdu1rtjkn9.jpg', 'สงขลาซู': 'https://dynamic-media-cdn.tripadvisor.com/media/photo-o/1c/39/bb/3c/songkhla-zoo.jpg?h=400&s=1&w=700', 'ดำน้ำดูปะการังเกาะราชา': 'https://i.world-tourism.org/m/racha-island-snorkeling-tour-by-speedboat-from-phuket-d349-110534P184-1.jpg', 'บลูทรี ภูเก็ต': 'https://media3.thrillophilia.com/filestore/ghuweaqb1dw6ih06xtu3v9bpdbf0_blue-tree-water-park.jpg'}


def _wikipedia_image(query: str):
    """ขั้นตอนที่ 1-2: ค้นหาใน Wikipedia (th แล้วค่อย en) ด้วยคำค้นที่ให้มา"""
    for lang in WIKI_LANGS:
        try:
            search_resp = requests.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 1},
                headers=WIKI_HEADERS, timeout=8,
            )
            search_resp.raise_for_status()
            hits = search_resp.json().get("query", {}).get("search", [])
            if not hits:
                continue

            title = hits[0]["title"]
            summary_resp = requests.get(
                f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}",
                headers=WIKI_HEADERS, timeout=8,
            )
            if summary_resp.status_code != 200:
                continue

            data = summary_resp.json()
            thumb = data.get("thumbnail") or data.get("originalimage") or {}
            if thumb.get("source"):
                return thumb["source"]
        except Exception:
            continue
    return None


def _wikimedia_commons_image(query: str):
    """ค้นหาใน Wikimedia Commons โดยตรง (คลังรูปภาพเสรีของ Wikipedia) — เผื่อสถานที่
    ไม่มีบทความ Wikipedia แต่มีรูปอยู่ใน Commons"""
    try:
        resp = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrnamespace": 6,  # ไฟล์ (File:) namespace เท่านั้น
                "gsrsearch": query,
                "gsrlimit": 1,
                "prop": "imageinfo",
                "iiprop": "url",
                "iiurlwidth": 800,
                "format": "json",
            },
            headers=WIKI_HEADERS, timeout=8,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            imageinfo = page.get("imageinfo", [])
            if imageinfo:
                info = imageinfo[0]
                return info.get("thumburl") or info.get("url")
    except Exception:
        pass
    return None


def _openverse_image(query: str):
    """ขั้นตอนที่ 4 (fallback สุดท้าย): Openverse API — คลังรูปลิขสิทธิ์เสรีที่รวมจาก
    Flickr, Europeana ฯลฯ ไม่ต้องใช้ API key สำหรับการค้นหาพื้นฐาน"""
    try:
        resp = requests.get(
            "https://api.openverse.org/v1/images/",
            params={"q": query, "page_size": 1, "license_type": "all-cc"},
            headers=OPENVERSE_HEADERS, timeout=8,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return results[0].get("thumbnail") or results[0].get("url")
    except Exception:
        pass
    return None


@st.cache_data(ttl=604800, show_spinner=False)
def fetch_place_image(name: str, province: str = ""):
    """
    ดึงรูปภาพจริงของสถานที่ ลำดับการค้นหา:
      1-2) Wikipedia (th แล้ว en) ค้นหาด้วย "ชื่อสถานที่ + จังหวัด" เพื่อลดโอกาสจับคู่ผิด
           (เช่น ชื่อสถานที่ซ้ำกันคนละจังหวัด)
      3)   Wikimedia Commons โดยตรง เผื่อสถานที่ไม่มีบทความ Wikipedia แต่มีรูปอยู่ใน Commons
      4)   Openverse API เป็น fallback สุดท้าย ก่อนไปใช้ไอคอนแทน

    ครอบคลุมสถานที่ทั่วไปอย่างห้าง ส่วนตัว ตลาด หรือสวนสนุกได้มากกว่าเดิม แต่ระบบภายนอก
    ไม่รับประกันผลลัพธ์ 100% เสมอไป — หากต้องการรูปที่แม่นยำแน่นอน ให้ใส่ image_url ใน
    travel_data.csv สำหรับแถวนั้นแทน (ดู place_image_or_icon ด้านล่าง)
    """
    query = f"{name} {province}".strip() if province else name

    image_url = _wikipedia_image(query)
    if image_url:
        return image_url

    image_url = _wikimedia_commons_image(query)
    if image_url:
        return image_url

    image_url = _openverse_image(query)
    if image_url:
        return image_url

    return None


def _download_image_bytes(url: str):
    """ดาวน์โหลดรูปจาก URL ให้ Streamlit แสดงเป็น bytes ลดปัญหา hotlink/รูปเสีย"""
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        resp = requests.get(
            url.strip(),
            headers={
                "User-Agent": "Mozilla/5.0 TravelMatch/1.0",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
            timeout=12,
            allow_redirects=True,
        )
        resp.raise_for_status()
        content = resp.content
        ctype = (resp.headers.get("content-type") or "").lower()
        is_image = (
            ctype.startswith("image/")
            or content.startswith(b"\xff\xd8\xff")
            or content.startswith(b"\x89PNG")
            or content.startswith(b"GIF8")
            or (content.startswith(b"RIFF") and b"WEBP" in content[:16])
        )
        if is_image and len(content) > 500:
            return content
    except Exception:
        pass
    return None


@st.cache_data(ttl=604800, show_spinner=False)
def _cached_image_bytes(url: str):
    return _download_image_bytes(url)


def place_image_or_icon(row, height_px=160):
    """ใช้รูปที่กำหนดใน CSV/override ก่อนเสมอ
    ถ้า URL ใช้ไม่ได้จึงค่อยค้นหารูปออนไลน์
    """
    name = str(row["name"]).strip()
    province = str(row.get("province", "")).strip()

    candidates = []

    # 1) Exact override ในโค้ด
    override = MANUAL_IMAGE_OVERRIDES.get(name)
    if isinstance(override, str) and override.strip():
        candidates.append(override.strip())

    # 2) image_url จาก CSV
    manual_url = row.get("image_url") if hasattr(row, "get") else None
    if isinstance(manual_url, str) and manual_url.strip():
        candidates.append(manual_url.strip())

    # 3) ค้นหาออนไลน์เฉพาะเมื่อ 1-2 ใช้ไม่ได้
    # ใช้ฟังก์ชันเดิมของโปรเจกต์ที่ค้นหา Wikipedia -> Wikimedia -> Openverse
    try:
        found = fetch_place_image(name, province)
        if found:
            candidates.append(found)
    except Exception:
        pass

    # ตัด URL ซ้ำ
    unique = []
    seen = set()
    for url in candidates:
        if url and url not in seen:
            seen.add(url)
            unique.append(url)

    for url in unique:
        image_bytes = _cached_image_bytes(url)
        if image_bytes:
            st.image(BytesIO(image_bytes), use_container_width=True)
            return

    # ไม่มีรูปที่ใช้ได้เลย จึงค่อยใช้ไอคอน
    icon = TYPE_ICON.get(row["type"], TYPE_ICON["default"])
    color = TYPE_COLOR.get(row["type"], TYPE_COLOR["default"])
    st.markdown(
        f"<div style='font-size:{int(height_px*0.4)}px;text-align:center;"
        f"padding:{int(height_px*0.15)}px 0;background:{color};border-radius:14px;'>{icon}</div>",
        unsafe_allow_html=True,
    )

# ----------------------------------------------------------------------------
# ส่วนจัดการข้อมูล (3.8 ข้อ 2): นำข้อมูลสถานที่ท่องเที่ยวจากไฟล์ CSV เข้าสู่ระบบ
# ----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data():
    df = pd.read_csv(get_data_file())

    # ตรวจสอบความถูกต้องของข้อมูลก่อนนำไปประมวลผล (ตาม 3.8 ข้อ 2)
    required_cols = [
        "name", "province", "type", "cost", "duration_days", "review_score",
        "distance_km", "popularity", "activities", "season", "travel_style",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"ไฟล์ข้อมูลขาดคอลัมน์: {', '.join(missing)}")
        return pd.DataFrame()

    # image_url เป็นคอลัมน์ทางเลือก — ถ้าไม่มีในไฟล์ ให้เพิ่มเป็นค่าว่างไว้ก่อน
    # เพื่อให้ place_image_or_icon() เรียก row.get("image_url") ได้เสมอ
    if "image_url" not in df.columns:
        df["image_url"] = ""

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
        if st.button("← ย้อนกลับ"):
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
                place_image_or_icon(row)
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

    if st.button("← ย้อนกลับ"):
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

    place_image_or_icon(place, height_px=320)

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
