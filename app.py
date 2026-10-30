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
# 1. 頁面配置與高質感 Mobile-First CSS
# -------------------------------------------------------------
st.set_page_config(
    page_title="NutriSnap - 你的個人AI減重營養師",
    page_icon="🥑",
    layout="centered",
    initial_sidebar_state="collapsed"
)

CUSTOM_CSS = """
<style>
/* 完全隱藏 Streamlit 原生頂部工具列、選單、分享按鈕與頁尾 */
header[data-testid="stHeader"], #MainMenu, footer, .stAppDeployButton {
    display: none !important;
    visibility: hidden !important;
}

/* 針對行動端進行排版優化 */
.main .block-container {
    padding-top: 1.2rem !important;
    padding-bottom: 3rem !important;
    max-width: 540px !important;
    margin: 0 auto !important;
}

/* 質感卡片與陰影 */
.card {
    background: #FFFFFF;
    border-radius: 20px;
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: 0 8px 24px rgba(149, 157, 165, 0.08);
    border: 1px solid #F1F5F9;
}

/* 核心指標排版 */
.calorie-board {
    background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
    border-radius: 24px;
    padding: 24px;
    color: white;
    text-align: center;
    margin-bottom: 20px;
}
.calorie-board .sub {
    font-size: 0.85rem;
    color: #94A3B8;
    letter-spacing: 0.5px;
}
.calorie-board .number {
    font-size: 2.8rem;
    font-weight: 800;
    margin: 6px 0;
    line-height: 1;
}

/* 營養素膠囊標籤 */
.pill-container {
    display: flex;
    justify-content: space-around;
    background: #F8FAFC;
    border-radius: 14px;
    padding: 10px;
    margin-top: 12px;
}
.pill-item {
    text-align: center;
}
.pill-label {
    font-size: 0.75rem;
    color: #64748B;
    font-weight: 500;
}
.pill-val {
    font-size: 0.95rem;
    font-weight: 700;
    color: #0F172A;
}

/* 按鈕美化 */
.stButton > button {
    border-radius: 14px !important;
    font-weight: 600 !important;
    height: 48px !important;
    transition: all 0.2s ease !important;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# -------------------------------------------------------------
# 2. 金鑰驗證與 Supabase 連線
# -------------------------------------------------------------
gemini_key = st.secrets.get("GEMINI_API_KEY", "")
supabase_url = st.secrets.get("SUPABASE_URL", "")
supabase_key = st.secrets.get("SUPABASE_KEY", "")

if not (gemini_key and supabase_url and supabase_key):
    st.error("請確認已在 Streamlit Secrets 正確設定 GEMINI_API_KEY、SUPABASE_URL 與 SUPABASE_KEY。")
    st.stop()

ai_client = genai.Client(api_key=gemini_key)
supabase: Client = create_client(supabase_url, supabase_key)

# -------------------------------------------------------------
# 3. 設備身分綁定 (Device ID)
# -------------------------------------------------------------
# 使用 query_params 模擬手機本地身分持久化
if "device_id" not in st.query_params:
    new_id = str(uuid.uuid4())[:8]
    st.query_params["device_id"] = new_id
    st.session_state["device_id"] = new_id
else:
    st.session_state["device_id"] = st.query_params["device_id"]

device_id = st.session_state["device_id"]

# -------------------------------------------------------------
# 4. 資料庫查詢與狀態管控
# -------------------------------------------------------------
def get_user_profile(d_id):
    res = supabase.table("user_profiles").select("*").eq("device_id", d_id).execute()
    return res.data[0] if res.data else None

def get_today_meals(d_id):
    today = datetime.utcnow().strftime("%Y-%m-%d 00:00:00")
    res = supabase.table("meals").select("*").eq("device_id", d_id).gte("created_at", today).order("created_at", desc=True).execute()
    return res.data or []

profile = get_user_profile(device_id)

# -------------------------------------------------------------
# 5. 門禁關卡：初次使用者健康評估 (Onboarding Flow)
# -------------------------------------------------------------
if not profile:
    st.markdown("""
    <div style='text-align: center; padding: 20px 0;'>
        <h2 style='font-weight: 800; color: #0F172A;'>👋 歡迎加入 NutriSnap</h2>
        <p style='color: #64748B; font-size: 0.95rem;'>為了精準估算您的專屬每日熱量額度 (TDEE)，請花 30 秒完成基本健康評估。</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("onboarding_form"):
        gender = st.radio("生理性別", ["女性", "男性"], horizontal=True)
        col_age, col_h = st.columns(2)
        with col_age:
            age = st.number_input("年齡 (歲)", min_value=12, max_value=99, value=26)
        with col_h:
            height = st.number_input("身高 (cm)", min_value=120.0, max_value=230.0, value=165.0, step=0.5)
        
        weight = st.number_input("體重 (kg)", min_value=35.0, max_value=200.0, value=60.0, step=0.5)
        
        activity = st.selectbox(
            "日常活動強度",
            [
                "久坐少動 (一般辦公室工作，幾乎不運動)",
                "輕度活動 (每週輕度運動 1-3 天)",
                "中度活動 (每週規律中度運動 3-5 天)",
                "高度運動 (每週高強度運動 6-7 天)"
            ]
        )
        
        goal = st.selectbox(
            "減重計畫目標",
            [
                "溫和健康減重 (每日熱量赤字 300 kcal)",
                "標準標準減重 (每日熱量赤字 500 kcal)",
                "維持目前體重 (無赤字)"
            ],
            index=1
        )
        
        submit = st.form_submit_button("✅ 計算 TDEE 並進入系統", type="primary", use_container_width=True)
        
        if submit:
            # 換算活動係數
            act_map = {
                "久坐少動 (一般辦公室工作，幾乎不運動)": 1.2,
                "輕度活動 (每週輕度運動 1-3 天)": 1.375,
                "中度活動 (每週規律中度運動 3-5 天)": 1.55,
                "高度運動 (每週高強度運動 6-7 天)": 1.725
            }
            factor = act_map[activity]
            
            # Mifflin-St Jeor 公式
            if gender == "男性":
                bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
            else:
                bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161
                
            tdee = bmr * factor
            deficit = 300 if "300" in goal else (500 if "500" in goal else 0)
            daily_budget = max(bmr, tdee - deficit) # 確保不低於 BMR 保障健康
            
            # 寫入雲端資料庫
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
            
            st.success("評估完成！已為您的手機建立專屬熱量預算。")
            st.rerun()
            
    st.stop()

# -------------------------------------------------------------
# 6. 正式首頁：每日剩餘熱量儀表板
# -------------------------------------------------------------
today_meals = get_today_meals(device_id)

consumed_cal = sum(m["calories"] for m in today_meals)
consumed_pro = sum(m["protein"] for m in today_meals)
consumed_carbs = sum(m["carbs"] for m in today_meals)
consumed_fat = sum(m["fat"] for m in today_meals)

budget = profile["daily_budget"]
remaining = budget - consumed_cal
remaining_color = "#10B981" if remaining >= 0 else "#EF4444"

st.markdown(f"""
<div class="calorie-board">
    <div class="sub">今日剩餘熱量預算</div>
    <div class="number" style="color: {remaining_color};">{remaining:,.0f} <span style="font-size: 1.2rem; font-weight: 500;">kcal</span></div>
    <div style="font-size: 0.85rem; color: #CBD5E1; margin-top: 4px;">
        目標 {budget:.0f} - 已攝取 {consumed_cal:.0f}
    </div>
    <div class="pill-container" style="background: rgba(255,255,255,0.08); margin-top: 16px;">
        <div class="pill-item">
            <div class="pill-label" style="color: #94A3B8;">蛋白質</div>
            <div class="pill-val" style="color: #FFFFFF;">{consumed_pro:.1f}g</div>
        </div>
        <div class="pill-item">
            <div class="pill-label" style="color: #94A3B8;">碳水化合物</div>
            <div class="pill-val" style="color: #FFFFFF;">{consumed_carbs:.1f}g</div>
        </div>
        <div class="pill-item">
            <div class="pill-label" style="color: #94A3B8;">脂肪</div>
            <div class="pill-val" style="color: #FFFFFF;">{consumed_fat:.1f}g</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 7. 拍照記錄與「分食/份量調整」核心模組
# -------------------------------------------------------------
st.markdown("<div class='card'>", unsafe_allow_html=True)
st.markdown("<h4 style='margin:0 0 12px 0; font-weight:700; color:#1E293B;'>📸 用餐當上記錄</h4>", unsafe_allow_html=True)

# 雙重相機調用相容性設計：手機端直接打開檔案選擇器，系統會主動詢問「拍照」或「從相簿挑選」
image_file = st.file_uploader("點擊立即拍照或挑選照片", type=["jpg", "jpeg", "png"], label_visibility="collapsed")

class FoodItem(BaseModel):
    name: str = Field(description="食物名稱")
    portion: str = Field(description="整盤食物的估計總重量或份量 (如: 250g, 1碗)")
    calories: float = Field(description="整盤熱量 (kcal)")
    protein: float = Field(description="整盤蛋白質 (g)")
    carbs: float = Field(description="整盤碳水化合物 (g)")
    fat: float = Field(description="整盤脂肪 (g)")

class MealAnalysis(BaseModel):
    meal_type: str = Field(description="判斷餐別 (早餐/午餐/晚餐/點心)")
    items: List[FoodItem] = Field(description="照片中的所有餐點食材細項")
    advice: str = Field(description="給減重者的實用簡明建議")

if image_file:
    img = Image.open(image_file)
    st.image(img, use_container_width=True)
    
    # 執行 AI 辨識
    if "current_analysis" not in st.session_state or st.session_state.get("last_uploaded_name") != image_file.name:
        with st.spinner("AI 正在深度解析餐點營養素..."):
            try:
                response = ai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        img,
                        "你是一位精準的專業營養師。請詳細辨識照片中的所有食物，"
                        "估算『整盤/整份』的重量、熱量(kcal)與三大營養素，並給出減重建議。"
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=MealAnalysis,
                        temperature=0.2
                    )
                )
                st.session_state["current_analysis"] = response.parsed
                st.session_state["last_uploaded_name"] = image_file.name
            except Exception as e:
                st.error(f"辨識發生問題：{e}")

    # 若有辨識結果，提供分食比例選擇
    if "current_analysis" in st.session_state:
        res: MealAnalysis = st.session_state["current_analysis"]
        
        st.markdown("---")
        st.markdown("##### 🍽️ 您實際吃了多少份量？(多人共食請自選)")
        
        portion_map = {
            "嚐鮮分食 (約 1/4 份)": 0.25,
            "朋友分食 (約 1/3 份)": 0.33,
            "兩人對半 (約 1/2 份)": 0.5,
            "獨自完食 (完整 1 份)": 1.0,
            "吃大份/續盤 (1.5 份)": 1.5,
            "雙倍份量 (2 份)": 2.0
        }
        selected_portion_label = st.radio("選擇實際攝取比例：", list(portion_map.keys()), index=3)
        multiplier = portion_map[selected_portion_label]

        # 計算按比例縮放後的營養數值
        base_cal = sum(i.calories for i in res.items)
        base_pro = sum(i.protein for i in res.items)
        base_carbs = sum(i.carbs for i in res.items)
        base_fat = sum(i.fat for i in res.items)

        actual_cal = base_cal * multiplier
        actual_pro = base_pro * multiplier
        actual_carbs = base_carbs * multiplier
        actual_fat = base_fat * multiplier

        # 呈現換算後的即時卡片
        st.info(f"👉 換算實際攝取：**{actual_cal:.0f} kcal** (蛋白質 {actual_pro:.1f}g | 碳水 {actual_carbs:.1f}g | 脂肪 {actual_fat:.1f}g)")
        
        if st.button("💾 確認記錄這餐", type="primary", use_container_width=True):
            items_payload = [{
                "name": i.name,
                "portion": i.portion,
                "actual_cal": round(i.calories * multiplier, 1)
            } for i in res.items]
            
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
            
            # 清理快取
            del st.session_state["current_analysis"]
            del st.session_state["last_uploaded_name"]
            st.success("記錄成功入庫！")
            st.rerun()

st.markdown("</div>", unsafe_allow_html=True)

# -------------------------------------------------------------
# 8. 今日記錄動態饋給 (Meal Timeline)
# -------------------------------------------------------------
st.markdown("<h5 style='font-weight: 700; color: #1E293B; margin-top: 24px;'>📋 今日已記餐點</h5>", unsafe_allow_html=True)

if not today_meals:
    st.caption("今天還沒有任何用餐記錄，拍下第一餐開始計算！")
else:
    for m in today_meals:
        st.markdown(f"""
        <div class="card" style="padding: 16px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:700; font-size:1.05rem; color:#0F172A;">🥣 {m['meal_type']}</span>
                <span style="font-weight:800; font-size:1.1rem; color:#2563EB;">{m['calories']:.0f} kcal</span>
            </div>
            <div style="font-size:0.8rem; color:#64748B; margin: 4px 0;">份量倍率：{m.get('portion_multiplier', 1.0)}x</div>
            <div style="font-size:0.85rem; color:#475569; background:#F8FAFC; padding:8px 12px; border-radius:10px; margin-top:8px;">
                💡 <b>建議：</b>{m.get('advice', '維持均衡飲食。')}
            </div>
        </div>
        """, unsafe_allow_html=True)
