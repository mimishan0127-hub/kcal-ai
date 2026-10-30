import streamlit as st
from PIL import Image
import pandas as pd
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime
from google import genai
from google.genai import types
from supabase import create_client, Client

# -------------------------------------------------------------
# 1. 頁面配置與 CSS 深度美化 (屏蔽 Streamlit Share/Toolbar 與原生邊界)
# -------------------------------------------------------------
st.set_page_config(
    page_title="NutriSnap AI",
    page_icon="🥑",
    layout="wide",
    initial_sidebar_state="collapsed"
)

CUSTOM_CSS = """
<style>
/* 1. 屏蔽 Streamlit 頂端導覽列、Share 按鈕、選單與頁尾 */
header[data-testid="stHeader"] {
    display: none !important;
}
#MainMenu {
    visibility: hidden !important;
}
footer {
    visibility: hidden !important;
}
.stAppDeployButton {
    display: none !important;
}

/* 2. 頁面邊界與背景質感優化 */
.main .block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    max-width: 900px !important;
}

/* 3. 卡片式設計 (Cards System) */
.glass-card {
    background: #FFFFFF;
    border-radius: 16px;
    padding: 18px 24px;
    margin-bottom: 16px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04);
    border: 1px solid #ECEFF1;
}

.kpi-title {
    font-size: 0.85rem;
    font-weight: 600;
    color: #78909C;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.kpi-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: #263238;
}

.kpi-unit {
    font-size: 0.9rem;
    font-weight: 400;
    color: #90A4AE;
    margin-left: 2px;
}

/* 4. 營養素徽章 (Badges) */
.nutrient-pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.8rem;
    font-weight: 600;
    margin-right: 6px;
}
.pill-protein { background: #E8F5E9; color: #2E7D32; }
.pill-carbs { background: #FFF3E0; color: #E65100; }
.pill-fat { background: #FFEBEE; color: #C62828; }

/* 5. 相機與上傳器現代化微調 */
div[data-testid="stCameraInput"] {
    border-radius: 16px;
    overflow: hidden;
}
button[kind="primary"] {
    border-radius: 12px !important;
    padding: 0.6rem 1.2rem !important;
    font-weight: 600 !important;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# -------------------------------------------------------------
# 2. 金鑰與雲端資料庫 (Supabase) 連線
# -------------------------------------------------------------
gemini_key = st.secrets.get("GEMINI_API_KEY", "")
supabase_url = st.secrets.get("SUPABASE_URL", "")
supabase_key = st.secrets.get("SUPABASE_KEY", "")

# 側邊欄容錯配置 (若 Secrets 未填寫)
with st.sidebar:
    st.markdown("### 🔐 服務設定")
    if not gemini_key:
        gemini_key = st.text_input("Gemini API Key", type="password")
    if not supabase_url:
        supabase_url = st.text_input("Supabase URL")
    if not supabase_key:
        supabase_key = st.text_input("Supabase Anon Key", type="password")

if not gemini_key:
    st.warning("請在側邊欄或 Secrets 設定 `GEMINI_API_KEY` 以啟動 AI 辨識。")
    st.stop()

# 初始化 Gemini Client
ai_client = genai.Client(api_key=gemini_key)

# 初始化 Supabase Client
supabase: Client = None
if supabase_url and supabase_key:
    try:
        supabase = create_client(supabase_url, supabase_key)
    except Exception as e:
        st.sidebar.error(f"雲端資料庫連線異常：{e}")

# -------------------------------------------------------------
# 3. 結構化 Schema 與資料庫存取層
# -------------------------------------------------------------
class FoodItem(BaseModel):
    name: str = Field(description="食物名稱")
    portion: str = Field(description="預估重量/份量 (如: 1碗, 150g)")
    calories: float = Field(description="熱量 (kcal)")
    protein: float = Field(description="蛋白質 (g)")
    carbs: float = Field(description="碳水化合物 (g)")
    fat: float = Field(description="脂肪 (g)")

class MealAnalysis(BaseModel):
    meal_type: str = Field(description="判斷餐別 (早餐/午餐/晚餐/點心)")
    items: List[FoodItem] = Field(description="盤中所有辨識出的食材或料理")
    health_advice: str = Field(description="給減重者的實用簡明飲食建議")

def fetch_today_meals():
    """從雲端資料庫抓取當日餐點資料"""
    if not supabase:
        return []
    try:
        today_start = datetime.utcnow().strftime("%Y-%m-%d 00:00:00")
        response = supabase.table("meals").select("*").gte("created_at", today_start).order("created_at", desc=True).execute()
        return response.data
    except Exception as ex:
        st.sidebar.warning(f"雲端紀錄同步中斷: {ex}")
        return []

def save_meal_to_cloud(meal_type, calories, protein, carbs, fat, items, advice):
    """將辨識出的餐點寫入 Supabase"""
    if not supabase:
        return False
    try:
        record = {
            "meal_type": meal_type,
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "fat": fat,
            "items": items,
            "advice": advice
        }
        supabase.table("meals").insert(record).execute()
        return True
    except Exception as ex:
        st.error(f"寫入雲端失敗：{ex}")
        return False

# -------------------------------------------------------------
# 4. 個人代謝參數 (TDEE 與熱量赤字)
# -------------------------------------------------------------
with st.sidebar:
    st.markdown("---")
    st.markdown("### 🏃 體態與代謝參數")
    gender = st.selectbox("性別", ["男", "女"], index=0)
    age = st.number_input("年齡", value=28, min_value=12, max_value=100)
    height = st.number_input("身高 (cm)", value=172.0, min_value=100.0, max_value=240.0)
    weight = st.number_input("體重 (kg)", value=70.0, min_value=30.0, max_value=200.0)
    
    activity_factors = {
        "久坐 / 缺乏運動": 1.2,
        "輕度活動 (每週 1-3 天)": 1.375,
        "中度運動 (每週 3-5 天)": 1.55,
        "高強度訓練 (每週 6-7 天)": 1.725
    }
    selected_act = st.selectbox("日常活動量", list(activity_factors.keys()), index=1)
    
    # BMR (Mifflin-St Jeor)
    bmr = (10 * weight) + (6.25 * height) - (5 * age) + (5 if gender == "男" else -161)
    tdee = bmr * activity_factors[selected_act]
    
    deficit = st.select_slider("減重目標赤字 (kcal/天)", options=[0, 300, 500, 750], value=500)
    daily_budget = max(bmr, tdee - deficit)

# -------------------------------------------------------------
# 5. 主畫面：現代卡片儀表板 (Dashboard)
# -------------------------------------------------------------
# 讀取當天資料 (雲端優先，退回本機暫存)
cloud_meals = fetch_today_meals()

total_cal = sum(m["calories"] for m in cloud_meals)
total_protein = sum(m["protein"] for m in cloud_meals)
total_carbs = sum(m["carbs"] for m in cloud_meals)
total_fat = sum(m["fat"] for m in cloud_meals)
remaining_cal = daily_budget - total_cal

# 標題區
st.markdown("<h2 style='font-weight: 800; color: #1E293B; margin-bottom: 4px;'>🥑 NutriSnap AI</h2>", unsafe_allow_html=True)
st.caption("拍下餐點，AI 即時解析營養份量，自動雲端同步與監控剩餘額度。")

# 核心數據區塊
k1, k2, k3 = st.columns(3)
with k1:
    st.markdown(f"""
    <div class="glass-card">
        <div class="kpi-title">每日預算目標</div>
        <div class="kpi-value">{daily_budget:.0f}<span class="kpi-unit">kcal</span></div>
        <div style="font-size: 0.78rem; color: #90A4AE; margin-top: 4px;">TDEE {tdee:.0f} - 赤字 {deficit}</div>
    </div>
    """, unsafe_allow_html=True)

with k2:
    st.markdown(f"""
    <div class="glass-card">
        <div class="kpi-title">今日累計攝取</div>
        <div class="kpi-value">{total_cal:.0f}<span class="kpi-unit">kcal</span></div>
        <div style="font-size: 0.78rem; color: #90A4AE; margin-top: 4px;">已記錄 {len(cloud_meals)} 餐</div>
    </div>
    """, unsafe_allow_html=True)

with k3:
    rem_color = "#2E7D32" if remaining_cal >= 0 else "#C62828"
    status_text = "額度充足" if remaining_cal >= 0 else "熱量超標"
    st.markdown(f"""
    <div class="glass-card" style="border-left: 4px solid {rem_color};">
        <div class="kpi-title">剩餘可用額度</div>
        <div class="kpi-value" style="color: {rem_color};">{remaining_cal:.0f}<span class="kpi-unit">kcal</span></div>
        <div style="font-size: 0.78rem; color: {rem_color}; margin-top: 4px;">{status_text}</div>
    </div>
    """, unsafe_allow_html=True)

# 巨量營養素膠囊標籤
st.markdown(f"""
<div style="margin-bottom: 20px; display: flex; align-items: center;">
    <span style="font-size: 0.85rem; color: #607D8B; margin-right: 12px; font-weight: 600;">營養比例：</span>
    <span class="nutrient-pill pill-protein">蛋白質 {total_protein:.1f}g</span>
    <span class="nutrient-pill pill-carbs">碳水化合物 {total_carbs:.1f}g</span>
    <span class="nutrient-pill pill-fat">脂肪 {total_fat:.1f}g</span>
</div>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 6. 拍照與上傳區塊 (Cards Layout)
# -------------------------------------------------------------
st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
st.markdown("<h4 style='margin-top:0; font-weight: 700; color: #37474F;'>📸 拍照分析新餐點</h4>", unsafe_allow_html=True)

input_col1, input_col2 = st.columns([1, 1])
with input_col1:
    photo = st.camera_input("開啟相機鏡頭", label_visibility="collapsed")
with input_col2:
    uploaded = st.file_uploader("或選擇既有照片", type=["jpg", "jpeg", "png"], label_visibility="collapsed")

img_source = photo or uploaded

if img_source:
    image = Image.open(img_source)
    st.image(image, use_container_width=True)
    
    if st.button("✨ 辨識熱量並儲存至雲端", type="primary", use_container_width=True):
        with st.spinner("AI 正在精算各食材份量與熱量..."):
            try:
                # 呼叫 Gemini 進行多模態辨識與 JSON Schema 轉換
                prompt = (
                    "身為專業臨床營養師，請詳細辨識照片中每一項食材與配菜，推估重量與份量，"
                    "計算卡路里與蛋白質、碳水化合物、脂肪克數，並給予針對該餐的減重指導。"
                )
                response = ai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[image, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=MealAnalysis,
                        temperature=0.2,
                    ),
                )
                result: MealAnalysis = response.parsed

                # 計算該餐總計
                meal_cal = sum(i.calories for i in result.items)
                meal_pro = sum(i.protein for i in result.items)
                meal_carbs = sum(i.carbs for i in result.items)
                meal_fat = sum(i.fat for i in result.items)
                items_dict = [i.model_dump() for i in result.items]

                # 寫入 Supabase 資料庫
                if supabase:
                    save_meal_to_cloud(
                        meal_type=result.meal_type,
                        calories=meal_cal,
                        protein=meal_pro,
                        carbs=meal_carbs,
                        fat=meal_fat,
                        items=items_dict,
                        advice=result.health_advice
                    )
                    st.success("🎉 已成功儲存至雲端資料庫！")
                else:
                    st.warning("⚠️ 本地辨識完成，但未偵測到 Supabase 連線，未同步至雲端。")

                st.rerun()

            except Exception as e:
                st.error(f"辨識失敗：{e}")

st.markdown("</div>", unsafe_allow_html=True)

# -------------------------------------------------------------
# 7. 今日歷程卡片 (History Feed)
# -------------------------------------------------------------
st.markdown("<h4 style='font-weight: 700; color: #37474F; margin-top: 24px;'>🗓️ 今日飲食歷程</h4>", unsafe_allow_html=True)

if not cloud_meals:
    st.info("今日尚無飲食紀錄，拍下第一餐開始計算！")
else:
    for meal in cloud_meals:
        with st.container():
            st.markdown(f"""
            <div class="glass-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-size: 1.1rem; font-weight: 700; color: #263238;">🍽️ {meal.get('meal_type', '餐點')}</span>
                    <span style="font-size: 1.2rem; font-weight: 800; color: #1E88E5;">{meal.get('calories', 0):.0f} kcal</span>
                </div>
                <div style="margin-bottom: 12px;">
                    <span class="nutrient-pill pill-protein">蛋 {meal.get('protein', 0):.1f}g</span>
                    <span class="nutrient-pill pill-carbs">碳 {meal.get('carbs', 0):.1f}g</span>
                    <span class="nutrient-pill pill-fat">脂 {meal.get('fat', 0):.1f}g</span>
                </div>
                <div style="background: #F8FAFC; border-radius: 8px; padding: 10px 14px; font-size: 0.85rem; color: #455A64; margin-bottom: 8px;">
                    💡 <b>營養師評析：</b>{meal.get('advice', '無')}
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # 展開食材明細
            with st.expander("查看這餐的食材組成細項"):
                items = meal.get("items", [])
                if items:
                    df = pd.DataFrame(items)
                    df.columns = ["食物名稱", "預估份量", "熱量(kcal)", "蛋白質(g)", "碳水(g)", "脂肪(g)"]
                    st.dataframe(df, use_container_width=True, hide_index=True)
