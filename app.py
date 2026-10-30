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
# 1. 頁面配置與極致頂級質感 CSS (Apple Health / Modern Minimalist)
# -------------------------------------------------------------
st.set_page_config(
    page_title="NutriSnap Luxe",
    page_icon="✨",
    layout="centered",
    initial_sidebar_state="collapsed"
)

LUXE_CSS = """
<style>
/* 徹底抹除 Streamlit 原生頂部 Header、Toolbar、Share、選單與頁尾 */
header[data-testid="stHeader"], #MainMenu, footer, .stAppDeployButton {
    display: none !important;
    visibility: hidden !important;
}

/* 背景與主容器全螢幕手機比例 */
.stApp {
    background-color: #0A0D14 !important;
    color: #F1F5F9 !important;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, sans-serif !important;
}

.main .block-container {
    padding-top: 1.2rem !important;
    padding-bottom: 4rem !important;
    max-width: 480px !important;
    margin: 0 auto !important;
}

/* 奢華金屬黑晶卡片 */
.luxe-card {
    background: linear-gradient(180deg, rgba(26, 32, 46, 0.8) 0%, rgba(17, 24, 39, 0.95) 100%);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 24px;
    padding: 22px;
    margin-bottom: 18px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(16px);
}

/* 核心熱量能量環看板 */
.hero-board {
    background: radial-gradient(circle at 50% 0%, rgba(16, 185, 129, 0.15) 0%, rgba(10, 13, 20, 0) 70%),
                linear-gradient(180deg, #131A26 0%, #0E131F 100%);
    border: 1px solid rgba(16, 185, 129, 0.25);
    border-radius: 28px;
    padding: 28px 20px;
    text-align: center;
    margin-bottom: 20px;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

.hero-subtitle {
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #94A3B8;
}

.hero-number {
    font-size: 3.4rem;
    font-weight: 800;
    line-height: 1.1;
    margin: 8px 0;
    letter-spacing: -1px;
}

/* 營養膠囊儀表 */
.macro-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    margin-top: 18px;
}

.macro-box {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 16px;
    padding: 10px 6px;
    text-align: center;
}

.macro-name {
    font-size: 0.72rem;
    font-weight: 500;
    color: #94A3B8;
    margin-bottom: 3px;
}

.macro-val {
    font-size: 1.05rem;
    font-weight: 700;
    color: #FFFFFF;
}

/* 按鈕極致質感 */
.stButton > button {
    background: linear-gradient(135deg, #10B981 0%, #059669 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 16px !important;
    font-size: 0.95rem !important;
    font-weight: 700 !important;
    padding: 0.75rem 1.2rem !important;
    height: 50px !important;
    box-shadow: 0 6px 20px rgba(16, 185, 129, 0.3) !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 8px 24px rgba(16, 185, 129, 0.45) !important;
}

/* 輸入框美化 */
.stNumberInput input, .stSelectbox div[data-baseweb="select"] {
    background-color: #161D2B !important;
    color: #F8FAFC !important;
    border-radius: 14px !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
}

/* 自訂進度條顏色 */
.stProgress > div > div > div > div {
    background: linear-gradient(90deg, #10B981 0%, #34D399 100%) !important;
    border-radius: 8px;
}
</style>
"""
st.markdown(LUXE_CSS, unsafe_allow_html=True)

# -------------------------------------------------------------
# 2. 金鑰驗證與防禦型連線
# -------------------------------------------------------------
gemini_key = st.secrets.get("GEMINI_API_KEY", "")
supabase_url = st.secrets.get("SUPABASE_URL", "")
supabase_key = st.secrets.get("SUPABASE_KEY", "")

if not (gemini_key and supabase_url and supabase_key):
    st.error("金鑰未設定完整，請於 Streamlit Secrets 填入 GEMINI_API_KEY、SUPABASE_URL、SUPABASE_KEY。")
    st.stop()

ai_client = genai.Client(api_key=gemini_key)
supabase: Client = create_client(supabase_url, supabase_key)

# -------------------------------------------------------------
# 3. 設備識別碼綁定 (Device Token)
# -------------------------------------------------------------
if "device_id" not in st.query_params:
    assigned_id = f"dev_{str(uuid.uuid4())[:10]}"
    st.query_params["device_id"] = assigned_id
    st.session_state["device_id"] = assigned_id
else:
    st.session_state["device_id"] = st.query_params["device_id"]

device_id = st.session_state["device_id"]

# -------------------------------------------------------------
# 4. 安全資料庫存取層 (附帶 Exception 防崩潰)
# -------------------------------------------------------------
def safe_get_profile(d_id):
    try:
        res = supabase.table("user_profiles").select("*").eq("device_id", d_id).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None

def safe_get_today_meals(d_id):
    try:
        today_start = datetime.utcnow().strftime("%Y-%m-%d 00:00:00")
        res = supabase.table("meals").select("*").eq("device_id", d_id).gte("created_at", today_start).order("created_at", desc=True).execute()
        return res.data or []
    except Exception:
        return []

profile = safe_get_profile(device_id)

# -------------------------------------------------------------
# 5. 精品級健康迎賓門禁 (Onboarding Gatekeeper)
# -------------------------------------------------------------
if not profile:
    st.markdown("""
    <div style='text-align: center; padding: 24px 0 10px 0;'>
        <div style='font-size: 2.2rem; margin-bottom: 6px;'>🥑</div>
        <h2 style='font-weight: 800; letter-spacing: -0.5px; color: #FFFFFF; margin: 0;'>NutriSnap Luxe</h2>
        <p style='color: #94A3B8; font-size: 0.88rem; margin-top: 8px;'>設定您的身體密碼，開啟 AI 智慧熱量管家</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("luxe_onboarding"):
        st.markdown("<div class='luxe-card'>", unsafe_allow_html=True)
        gender = st.radio("生理性別", ["女性", "男性"], horizontal=True)
        
        c1, c2 = st.columns(2)
        with c1:
            age = st.number_input("年齡", min_value=12, max_value=100, value=27)
        with c2:
            height = st.number_input("身高 (cm)", min_value=120.0, max_value=230.0, value=166.0, step=0.5)
        
        weight = st.number_input("體重 (kg)", min_value=30.0, max_value=200.0, value=58.5, step=0.5)
        
        act = st.selectbox(
            "日常活動強度",
            [
                "久坐少動 (辦公室/低步數，係數 1.2)",
                "輕度活動 (每週運動 1-3 天，係數 1.375)",
                "中度活動 (每週運動 3-5 天，係數 1.55)",
                "高度運動 (每週高強度運動，係數 1.725)"
            ]
        )
        
        deficit_choice = st.select_slider(
            "每日熱量赤字目標",
            options=[0, 300, 500, 750],
            value=400,
            format_func=lambda x: f"{x} kcal (維持)" if x == 0 else f"-{x} kcal/天"
        )
        
        btn = st.form_submit_button("啟動專屬代謝檔案", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if btn:
            act_map = {
                "久坐少動 (辦公室/低步數，係數 1.2)": 1.2,
                "輕度活動 (每週運動 1-3 天，係數 1.375)": 1.375,
                "中度活動 (每週運動 3-5 天，係數 1.55)": 1.55,
                "高度運動 (每週高強度運動，係數 1.725)": 1.725
            }
            factor = act_map[act]
            
            # 精算 BMR (Mifflin-St Jeor)
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
                st.error(f"建立設定檔失敗，請確認已執行修復 SQL：{e}")

    st.stop()

# -------------------------------------------------------------
# 6. 正式首頁：Apple Health 旗艦風格儀表板
# -------------------------------------------------------------
today_meals = safe_get_today_meals(device_id)

consumed_cal = sum(m.get("calories", 0) for m in today_meals)
consumed_pro = sum(m.get("protein", 0) for m in today_meals)
consumed_carbs = sum(m.get("carbs", 0) for m in today_meals)
consumed_fat = sum(m.get("fat", 0) for m in today_meals)

budget = profile["daily_budget"]
remaining = budget - consumed_cal

rem_color = "#10B981" if remaining >= 0 else "#F43F5E"
rem_status = "額度充裕" if remaining >= 0 else "已超過預算"

st.markdown(f"""
<div class="hero-board">
    <div class="hero-subtitle">REMAINING CALORIES</div>
    <div class="hero-number" style="color: {rem_color};">
        {remaining:,.0f}
        <span style="font-size: 1.2rem; font-weight: 500; color: #94A3B8;">kcal</span>
    </div>
    <div style="font-size: 0.85rem; color: #94A3B8;">
        今日預算 {budget:,.0f} &nbsp;·&nbsp; 已攝取 <span style="color: #FFFFFF; font-weight:600;">{consumed_cal:,.0f}</span>
    </div>
    
    <div class="macro-grid">
        <div class="macro-box">
            <div class="macro-name">蛋白質</div>
            <div class="macro-val" style="color: #34D399;">{consumed_pro:.1f}g</div>
        </div>
        <div class="macro-box">
            <div class="macro-name">碳水</div>
            <div class="macro-val" style="color: #FBBF24;">{consumed_carbs:.1f}g</div>
        </div>
        <div class="macro-box">
            <div class="macro-name">脂肪</div>
            <div class="macro-val" style="color: #F87171;">{consumed_fat:.1f}g</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 7. 用餐拍照記錄與即時共食分量比例切換
# -------------------------------------------------------------
st.markdown("<div class='luxe-card'>", unsafe_allow_html=True)
st.markdown("<div style='font-size: 1.05rem; font-weight: 700; color: #FFFFFF; margin-bottom: 12px;'>📸 捕捉這餐美食</div>", unsafe_allow_html=True)

# 手機相機友善上傳元件
photo_upload = st.file_uploader(
    "拍照或上傳餐點",
    type=["jpg", "jpeg", "png"],
    label_visibility="collapsed"
)

class FoodItem(BaseModel):
    name: str = Field(description="食物名稱")
    portion: str = Field(description="整盤食物的估算重量或份量 (例: 200g, 1碗)")
    calories: float = Field(description="整盤熱量 (kcal)")
    protein: float = Field(description="整盤蛋白質 (g)")
    carbs: float = Field(description="整盤碳水 (g)")
    fat: float = Field(description="整盤脂肪 (g)")

class MealAnalysis(BaseModel):
    meal_type: str = Field(description="判斷餐別 (早餐/午餐/晚餐/點心)")
    items: List[FoodItem] = Field(description="辨識出的所有食材")
    advice: str = Field(description="精簡、專業的減重營養指導")

if photo_upload:
    image = Image.open(photo_upload)
    st.image(image, use_container_width=True)
    
    # AI 辨識分析
    if "analysis_cache" not in st.session_state or st.session_state.get("cached_file") != photo_upload.name:
        with st.spinner("✨ 頂級 AI 正在精算盤中所有食材營養..."):
            try:
                response = ai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        image,
                        "你是一位精通食材成分與熱量計算的專業營養師。請嚴謹辨識照片中整盤所有料理，"
                        "估算各項目重量、整盤熱量(kcal)與三大營養素，並給予減重方針。"
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=MealAnalysis,
                        temperature=0.2
                    )
                )
                st.session_state["analysis_cache"] = response.parsed
                st.session_state["cached_file"] = photo_upload.name
            except Exception as e:
                st.error(f"辨識遇到問題：{e}")

    if "analysis_cache" in st.session_state:
        res: MealAnalysis = st.session_state["analysis_cache"]
        
        st.markdown("<div style='height: 1px; background: rgba(255,255,255,0.08); margin: 16px 0;'></div>", unsafe_allow_html=True)
        st.markdown("<div style='font-size: 0.9rem; font-weight: 600; color: #94A3B8; margin-bottom: 8px;'>👥 您實際吃了多少？(分食/共食自選)</div>", unsafe_allow_html=True)
        
        portion_options = {
            "嚐鮮分食 (約 1/4 份)": 0.25,
            "好友共食 (約 1/3 份)": 0.33,
            "兩人分半 (約 1/2 份)": 0.5,
            "一人獨享 (完整 1 份)": 1.0,
            "大份增量 (1.5 份)": 1.5,
            "雙倍份量 (2.0 份)": 2.0
        }
        portion_label = st.select_slider("攝取比例", options=list(portion_options.keys()), value="一人獨享 (完整 1 份)")
        multiplier = portion_options[portion_label]

        base_cal = sum(i.calories for i in res.items)
        base_pro = sum(i.protein for i in res.items)
        base_carbs = sum(i.carbs for i in res.items)
        base_fat = sum(i.fat for i in res.items)

        actual_cal = base_cal * multiplier
        actual_pro = base_pro * multiplier
        actual_carbs = base_carbs * multiplier
        actual_fat = base_fat * multiplier

        st.markdown(f"""
        <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 14px; padding: 14px; margin: 12px 0;">
            <div style="font-size: 0.8rem; color: #34D399; font-weight: 600;">換算您的實際攝取</div>
            <div style="font-size: 1.6rem; font-weight: 800; color: #FFFFFF; margin: 4px 0;">
                {actual_cal:.0f} <span style="font-size: 0.9rem; font-weight: 400; color: #94A3B8;">kcal</span>
            </div>
            <div style="font-size: 0.8rem; color: #CBD5E1;">
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
                st.success("✨ 已成功寫入雲端日誌！")
                st.rerun()
            except Exception as e:
                st.error(f"寫入資料庫失敗：{e}")

st.markdown("</div>", unsafe_allow_html=True)

# -------------------------------------------------------------
# 8. 今日餐點時間軸 (Timeline Cards)
# -------------------------------------------------------------
st.markdown("<div style='font-size: 1.05rem; font-weight: 700; color: #FFFFFF; margin: 24px 0 12px 4px;'>🗓️ 今日飲食時序</div>", unsafe_allow_html=True)

if not today_meals:
    st.markdown("""
    <div style="text-align: center; padding: 30px 10px; color: #64748B; font-size: 0.88rem;">
        今日尚無紀錄，拍下第一餐開始智慧減重旅程 ✨
    </div>
    """, unsafe_allow_html=True)
else:
    for m in today_meals:
        st.markdown(f"""
        <div class="luxe-card" style="padding: 18px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight: 700; font-size: 1.05rem; color: #FFFFFF;">🍽️ {m.get('meal_type', '餐點')}</span>
                <span style="font-weight: 800; font-size: 1.2rem; color: #34D399;">{m.get('calories', 0):.0f} kcal</span>
            </div>
            <div style="font-size: 0.78rem; color: #64748B; margin: 4px 0 10px 0;">
                份量：{m.get('portion_multiplier', 1.0)}x 比例
            </div>
            <div style="background: rgba(255,255,255,0.03); border-radius: 12px; padding: 10px 14px; font-size: 0.82rem; color: #CBD5E1; line-height: 1.4;">
                💡 {m.get('advice', '維持均衡飲食。')}
            </div>
        </div>
        """, unsafe_allow_html=True)
