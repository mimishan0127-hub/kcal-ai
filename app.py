import streamlit as st
from PIL import Image
import pandas as pd
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime
import uuid
from google import genai
from google.genai import types
from supabase import create_client, Client

# -------------------------------------------------------------
# 1. 頁面配置與現代純白清新質感 CSS (無縮排，徹底解決破版)
# -------------------------------------------------------------
st.set_page_config(
    page_title="NutriSnap AI",
    page_icon="🥗",
    layout="centered",
    initial_sidebar_state="collapsed"
)

CLEAN_LIGHT_CSS = """
<style>
/* 徹底抹除 Streamlit 原生頂部 Header、Toolbar、Share、選單與頁尾 */
header[data-testid="stHeader"], #MainMenu, footer, .stAppDeployButton {
    display: none !important;
    visibility: hidden !important;
}

/* 清新明亮底色與行動端版型寬度 */
.stApp {
    background-color: #F8FAFC !important;
    color: #1E293B !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
}

.main .block-container {
    padding-top: 1.2rem !important;
    padding-bottom: 3.5rem !important;
    max-width: 500px !important;
    margin: 0 auto !important;
}

/* 頂級純白陰影卡片 */
.white-card {
    background: #FFFFFF;
    border-radius: 20px;
    padding: 22px;
    margin-bottom: 16px;
    border: 1px solid #E2E8F0;
    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
}

/* 核心熱量儀表板看板 */
.dashboard-hero {
    background: linear-gradient(135deg, #059669 0%, #10B981 100%);
    border-radius: 24px;
    padding: 26px 20px;
    color: #FFFFFF;
    text-align: center;
    margin-bottom: 18px;
    box-shadow: 0 10px 25px rgba(16, 185, 129, 0.25);
}

.dashboard-hero-over {
    background: linear-gradient(135deg, #E11D48 0%, #F43F5E 100%) !important;
    box-shadow: 0 10px 25px rgba(244, 63, 94, 0.25) !important;
}

.hero-tag {
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    opacity: 0.9;
}

.hero-main-val {
    font-size: 3.2rem;
    font-weight: 800;
    line-height: 1.1;
    margin: 6px 0;
}

/* 營養素方塊排版 */
.macro-container {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    margin-top: 16px;
    background: rgba(255, 255, 255, 0.18);
    backdrop-filter: blur(8px);
    border-radius: 16px;
    padding: 12px 10px;
}

.macro-cell {
    flex: 1;
    text-align: center;
}

.macro-title {
    font-size: 0.72rem;
    font-weight: 500;
    color: rgba(255, 255, 255, 0.9);
}

.macro-number {
    font-size: 1.05rem;
    font-weight: 700;
    color: #FFFFFF;
}

/* 按鈕美化 */
.stButton > button {
    background: #059669 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 14px !important;
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    height: 48px !important;
    box-shadow: 0 4px 12px rgba(5, 150, 105, 0.25) !important;
    transition: all 0.2s ease !important;
}

.stButton > button:hover {
    background: #047857 !important;
}

/* 簡約輸入框 */
.stNumberInput input, .stSelectbox div[data-baseweb="select"] {
    background-color: #FFFFFF !important;
    border-radius: 12px !important;
    border: 1px solid #CBD5E1 !important;
}
</style>
"""
st.markdown(CLEAN_LIGHT_CSS, unsafe_allow_html=True)

# -------------------------------------------------------------
# 2. 金鑰驗證與資料庫連線
# -------------------------------------------------------------
gemini_key = st.secrets.get("GEMINI_API_KEY", "")
supabase_url = st.secrets.get("SUPABASE_URL", "")
supabase_key = st.secrets.get("SUPABASE_KEY", "")

if not (gemini_key and supabase_url and supabase_key):
    st.error("請確認 Streamlit Secrets 已填入 GEMINI_API_KEY、SUPABASE_URL 與 SUPABASE_KEY。")
    st.stop()

ai_client = genai.Client(api_key=gemini_key)
supabase: Client = create_client(supabase_url, supabase_key)

# -------------------------------------------------------------
# 3. 手機設備識別碼 (Device ID) 綁定
# -------------------------------------------------------------
if "device_id" not in st.query_params:
    assigned_id = f"dev_{str(uuid.uuid4())[:8]}"
    st.query_params["device_id"] = assigned_id
    st.session_state["device_id"] = assigned_id
else:
    st.session_state["device_id"] = st.query_params["device_id"]

device_id = st.session_state["device_id"]

# -------------------------------------------------------------
# 4. 資料庫查詢（含防崩潰容錯）
# -------------------------------------------------------------
def get_user_profile(d_id):
    try:
        res = supabase.table("user_profiles").select("*").eq("device_id", d_id).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None

def get_today_meals(d_id):
    try:
        today_start = datetime.utcnow().strftime("%Y-%m-%d 00:00:00")
        res = supabase.table("meals").select("*").eq("device_id", d_id).gte("created_at", today_start).order("created_at", desc=True).execute()
        return res.data or []
    except Exception:
        return []

profile = get_user_profile(device_id)

# -------------------------------------------------------------
# 5. 門禁關卡：初次健康問卷（尚未建立 TDEE 無法進入首頁）
# -------------------------------------------------------------
if not profile:
    st.markdown("""
<div style="text-align: center; padding: 20px 0 10px 0;">
<div style="font-size: 2.2rem; margin-bottom: 4px;">🥗</div>
<h2 style="font-weight: 800; color: #0F172A; margin: 0;">NutriSnap AI</h2>
<p style="color: #64748B; font-size: 0.9rem; margin-top: 6px;">請完成基本體態設定，系統將為您推算每日專屬熱量預算</p>
</div>
""", unsafe_allow_html=True)

    with st.form("onboarding_form"):
        st.markdown("<div class='white-card'>", unsafe_allow_html=True)
        gender = st.radio("生理性別", ["女性", "男性"], horizontal=True)
        
        c1, c2 = st.columns(2)
        with c1:
            age = st.number_input("年齡", min_value=12, max_value=99, value=26)
        with c2:
            height = st.number_input("身高 (cm)", min_value=120.0, max_value=230.0, value=165.0, step=0.5)
            
        weight = st.number_input("體重 (kg)", min_value=30.0, max_value=200.0, value=58.0, step=0.5)
        
        act = st.selectbox(
            "日常活動強度",
            [
                "久坐少動 (一般上班族/辦公室)",
                "輕度活動 (每週輕度運動 1-3 天)",
                "中度活動 (每週中度運動 3-5 天)",
                "高度運動 (每週高強度運動 6-7 天)"
            ]
        )
        
        deficit_choice = st.select_slider(
            "減重熱量赤字目標",
            options=[0, 300, 500, 750],
            value=400,
            format_func=lambda x: f"{x} kcal (維持體重)" if x == 0 else f"-{x} kcal/天 (減重)"
        )
        
        btn = st.form_submit_button("計算 TDEE 並進入首頁", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if btn:
            act_map = {
                "久坐少動 (一般上班族/辦公室)": 1.2,
                "輕度活動 (每週輕度運動 1-3 天)": 1.375,
                "中度活動 (每週中度運動 3-5 天)": 1.55,
                "高度運動 (每週高強度運動 6-7 天)": 1.725
            }
            factor = act_map[act]
            
            # Mifflin-St Jeor 公式
            if gender == "男性":
                bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
            else:
                bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161
                
            tdee = bmr * factor
            daily_budget = max(bmr, tdee - deficit_choice)

            try:
                supabase.table("user_profiles").insert({
                    "device_id": device_id,
                    "gender": gender,
                    "age": age,
                    "height": height,
                    "weight": weight,
                    "activity_factor": factor,
                    "bmr": bmr,
                    "tdee": tdee,
                    "daily_budget": daily_budget
                }).execute()
                st.rerun()
            except Exception as e:
                st.error(f"儲存失敗，請確認 Supabase 資料表已建立：{e}")

    st.stop()

# -------------------------------------------------------------
# 6. 正式首頁：清新純白/翡翠綠儀表板
# -------------------------------------------------------------
today_meals = get_today_meals(device_id)

consumed_cal = sum(m.get("calories", 0) for m in today_meals)
consumed_pro = sum(m.get("protein", 0) for m in today_meals)
consumed_carbs = sum(m.get("carbs", 0) for m in today_meals)
consumed_fat = sum(m.get("fat", 0) for m in today_meals)

budget = profile["daily_budget"]
remaining = budget - consumed_cal
is_over = remaining < 0

hero_class = "dashboard-hero dashboard-hero-over" if is_over else "dashboard-hero"
hero_status_text = "今日剩餘可用熱量" if not is_over else "已超出今日預算"

# 嚴格保持左對齊、無縮排，徹底阻絕 Markdown 代碼塊解析錯誤
st.markdown(f"""
<div class="{hero_class}">
<div class="hero-tag">{hero_status_text}</div>
<div class="hero-main-val">{abs(remaining):,.0f} <span style="font-size: 1.1rem; font-weight: 500;">kcal</span></div>
<div style="font-size: 0.85rem; opacity: 0.95;">
每日目標 {budget:,.0f} · 今日已攝取 {consumed_cal:,.0f}
</div>
<div class="macro-container">
<div class="macro-cell">
<div class="macro-title">蛋白質</div>
<div class="macro-number">{consumed_pro:.1f}g</div>
</div>
<div class="macro-cell">
<div class="macro-title">碳水化合物</div>
<div class="macro-number">{consumed_carbs:.1f}g</div>
</div>
<div class="macro-cell">
<div class="macro-title">脂肪</div>
<div class="macro-number">{consumed_fat:.1f}g</div>
</div>
</div>
</div>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 7. 拍照記錄與多人共食/份量自選區塊
# -------------------------------------------------------------
st.markdown("<div class='white-card'>", unsafe_allow_html=True)
st.markdown("<h4 style='margin:0 0 12px 0; font-weight:700; color:#0F172A;'>📸 拍照記錄這餐</h4>", unsafe_allow_html=True)

# 透過檔案選擇器自動喚醒手機相機或相簿
uploaded_photo = st.file_uploader(
    "點擊拍照或從相簿選擇",
    type=["jpg", "jpeg", "png"],
    label_visibility="collapsed"
)

class FoodItem(BaseModel):
    name: str = Field(description="食物名稱")
    portion: str = Field(description="整盤食物的估算重量或份量 (例: 200g, 1碗)")
    calories: float = Field(description="整盤總熱量 (kcal)")
    protein: float = Field(description="整盤總蛋白質 (g)")
    carbs: float = Field(description="整盤總碳水 (g)")
    fat: float = Field(description="整盤總脂肪 (g)")

class MealAnalysis(BaseModel):
    meal_type: str = Field(description="判斷餐別 (早餐/午餐/晚餐/點心)")
    items: List[FoodItem] = Field(description="辨識出的所有食材細項")
    advice: str = Field(description="簡明實用的減重營養指導")

if uploaded_photo:
    image = Image.open(uploaded_photo)
    st.image(image, use_container_width=True)
    
    if "analysis_cache" not in st.session_state or st.session_state.get("cached_file") != uploaded_photo.name:
        with st.spinner("AI 正在解析餐點營養成份..."):
            try:
                response = ai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        image,
                        "你是一位專業營養師。請詳細辨識照片中整盤所有的料理與食材，"
                        "估算各項目重量、整盤熱量(kcal)與三大營養素，並給予減重方針。"
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=MealAnalysis,
                        temperature=0.2
                    )
                )
                st.session_state["analysis_cache"] = response.parsed
                st.session_state["cached_file"] = uploaded_photo.name
            except Exception as e:
                st.error(f"辨識失敗：{e}")

    if "analysis_cache" in st.session_state:
        res: MealAnalysis = st.session_state["analysis_cache"]
        
        st.markdown("<hr style='border:0; border-top:1px solid #E2E8F0; margin:16px 0;'>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:0.9rem; font-weight:700; color:#334155; margin-bottom:8px;'>🍽️ 實際食用比例 (共食/分食調整)：</div>", unsafe_allow_html=True)
        
        portion_map = {
            "嚐鮮分食 (約 1/4 份)": 0.25,
            "好友共食 (約 1/3 份)": 0.33,
            "兩人分半 (約 1/2 份)": 0.5,
            "獨自完食 (完整 1 份)": 1.0,
            "大份增量 (1.5 份)": 1.5,
            "雙倍份量 (2.0 份)": 2.0
        }
        portion_label = st.radio("選擇比例", list(portion_map.keys()), index=3, label_visibility="collapsed")
        multiplier = portion_map[portion_label]

        # 比例折算
        base_cal = sum(i.calories for i in res.items)
        base_pro = sum(i.protein for i in res.items)
        base_carbs = sum(i.carbs for i in res.items)
        base_fat = sum(i.fat for i in res.items)

        actual_cal = base_cal * multiplier
        actual_pro = base_pro * multiplier
        actual_carbs = base_carbs * multiplier
        actual_fat = base_fat * multiplier

        st.markdown(f"""
<div style="background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 12px; padding: 12px; margin: 12px 0;">
<div style="font-size: 0.78rem; color: #166534; font-weight: 600;">換算後實際攝取</div>
<div style="font-size: 1.5rem; font-weight: 800; color: #15803D; margin: 2px 0;">
{actual_cal:.0f} <span style="font-size: 0.85rem; font-weight: 500; color: #64748B;">kcal</span>
</div>
<div style="font-size: 0.8rem; color: #334155;">
蛋白質 {actual_pro:.1f}g · 碳水 {actual_carbs:.1f}g · 脂肪 {actual_fat:.1f}g
</div>
</div>
""", unsafe_allow_html=True)

        if st.button("確認記入今日日誌", use_container_width=True):
            items_payload = [{
                "name": i.name,
                "portion": i.portion,
                "actual_cal": round(i.calories * multiplier, 1)
            } for i in res.items]
            
            try:
                supabase.table("meals").insert({
                    "device_id": device_id,
                    "meal_type": res.meal_type,
                    "portion_multiplier": multiplier,
                    "calories": actual_cal,
                    "protein": actual_pro,
                    "carbs": actual_carbs,
                    "fat": actual_fat,
                    "items": items_payload,
                    "advice": res.advice
                }).execute()
                
                del st.session_state["analysis_cache"]
                del st.session_state["cached_file"]
                st.success("記錄成功入庫！")
                st.rerun()
            except Exception as e:
                st.error(f"寫入雲端失敗：{e}")

st.markdown("</div>", unsafe_allow_html=True)

# -------------------------------------------------------------
# 8. 今日飲食時間軸
# -------------------------------------------------------------
st.markdown("<h4 style='font-weight: 700; color: #0F172A; margin: 20px 0 10px 4px;'>📋 今日飲食記錄</h4>", unsafe_allow_html=True)

if not today_meals:
    st.markdown("""
<div style="text-align: center; padding: 24px 10px; color: #94A3B8; font-size: 0.88rem;">
今日尚無紀錄，拍下第一餐開始計算！
</div>
""", unsafe_allow_html=True)
else:
    for m in today_meals:
        st.markdown(f"""
<div class="white-card" style="padding: 16px;">
<div style="display: flex; justify-content: space-between; align-items: center;">
<span style="font-weight: 700; font-size: 1.05rem; color: #0F172A;">🥣 {m.get('meal_type', '餐點')}</span>
<span style="font-weight: 800; font-size: 1.15rem; color: #059669;">{m.get('calories', 0):.0f} kcal</span>
</div>
<div style="font-size: 0.8rem; color: #64748B; margin: 3px 0 8px 0;">
實際份量：{m.get('portion_multiplier', 1.0)}x 比例
</div>
<div style="background: #F8FAFC; border-radius: 10px; padding: 10px 12px; font-size: 0.82rem; color: #475569; line-height: 1.4;">
💡 <b>建議：</b>{m.get('advice', '維持均衡飲食。')}
</div>
</div>
""", unsafe_allow_html=True)
