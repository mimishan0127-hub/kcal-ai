import streamlit as st
from PIL import Image
import pandas as pd
from pydantic import BaseModel, Field
from typing import List
from google import genai
from google.genai import types

# 網頁配置
st.set_page_config(page_title="AI 減重熱量與營養管家", page_icon="🥗", layout="wide")

# 1. 取得 API Key
api_key = st.secrets.get("GEMINI_API_KEY", None)
if not api_key:
    api_key = st.sidebar.text_input("輸入 Gemini API Key", type="password")
    if not api_key:
        st.info("請於側邊欄輸入 Gemini API Key 或設定 Streamlit Secrets。")
        st.stop()

client = genai.Client(api_key=api_key)

# 2. 定義餐點辨識結構化格式
class FoodItem(BaseModel):
    name: str = Field(description="食物名稱")
    portion: str = Field(description="估算份量或重量 (例如: 150g, 1碗)")
    calories: float = Field(description="估計熱量 (kcal)")
    protein: float = Field(description="蛋白質 (g)")
    carbs: float = Field(description="碳水化合物 (g)")
    fat: float = Field(description="脂肪 (g)")

class MealAnalysis(BaseModel):
    meal_type: str = Field(description="判斷餐別 (早餐/午餐/晚餐/點心)")
    items: List[FoodItem] = Field(description="盤中所有辨識出的食材或料理")
    health_advice: str = Field(description="針對減重與營養均衡的簡短建議")

# 3. 初始化 Session State 儲存當日紀錄
if "meals_log" not in st.session_state:
    st.session_state.meals_log = []

# 4. 側邊欄：個人數值與 TDEE 計算
st.sidebar.header("⚙️ 個人健康設定 (TDEE)")
gender = st.sidebar.selectbox("生理性別", ["男", "女"])
age = st.sidebar.number_input("年齡", min_value=15, max_value=100, value=28)
height = st.sidebar.number_input("身高 (cm)", min_value=100.0, max_value=250.0, value=172.0)
weight = st.sidebar.number_input("體重 (kg)", min_value=30.0, max_value=200.0, value=70.0)

activity_levels = {
    "久坐 / 幾乎不運動 (1.2)": 1.2,
    "輕度活動 (每週輕度運動 1-3 天) (1.375)": 1.375,
    "中度活動 (每週中度運動 3-5 天) (1.55)": 1.55,
    "高強度活動 (每週高強度運動 6-7 天) (1.725)": 1.725
}
activity_choice = st.sidebar.selectbox("日常活動量", list(activity_levels.keys()))
activity_factor = activity_levels[activity_choice]

# Mifflin-St Jeor 公式計算 BMR
if gender == "男":
    bmr = 10 * weight + 6.25 * height - 5 * age + 5
else:
    bmr = 10 * weight + 6.25 * height - 5 * age - 161

tdee = bmr * activity_factor

deficit_choice = st.sidebar.select_slider(
    "減重目標赤字 (kcal/日)",
    options=[0, 300, 500, 750],
    value=500
)

# 每日目標攝取 (確保不低於 BMR 保持健康安全)
daily_calorie_target = max(bmr, tdee - deficit_choice)

st.sidebar.markdown("---")
st.sidebar.metric("基礎代謝 (BMR)", f"{bmr:.0f} kcal")
st.sidebar.metric("每日總消耗 (TDEE)", f"{tdee:.0f} kcal")
st.sidebar.metric("每日目標攝取", f"{daily_calorie_target:.0f} kcal")

# 5. 主畫面：儀表板與剩餘熱量計算
st.title("📸 AI 拍照熱量與減重追蹤器")

total_consumed_cal = sum(item["熱量 (kcal)"] for meal in st.session_state.meals_log for item in meal["items"])
total_consumed_protein = sum(item["蛋白質 (g)"] for meal in st.session_state.meals_log for item in meal["items"])
total_consumed_carbs = sum(item["碳水 (g)"] for meal in st.session_state.meals_log for item in meal["items"])
total_consumed_fat = sum(item["脂肪 (g)"] for meal in st.session_state.meals_log for item in meal["items"])

remaining_cal = daily_calorie_target - total_consumed_cal

# 頂部儀表板
col1, col2, col3, col4 = st.columns(4)
col1.metric("今日熱量預算", f"{daily_calorie_target:.0f} kcal")
col2.metric("已攝取熱量", f"{total_consumed_cal:.0f} kcal")
col3.metric(
    "剩餘可用熱量", 
    f"{remaining_cal:.0f} kcal", 
    delta=f"{remaining_cal:.0f} kcal",
    delta_color="normal" if remaining_cal >= 0 else "inverse"
)
col4.metric("蛋白質累積", f"{total_consumed_protein:.1f} g")

# 熱量進度條
progress_ratio = min(1.0, max(0.0, total_consumed_cal / daily_calorie_target)) if daily_calorie_target > 0 else 0
st.progress(progress_ratio)

st.markdown("---")

# 6. 拍照與上傳辨識區
st.subheader("📷 記錄餐點")
col_input, col_preview = st.columns([1, 1])

with col_input:
    photo = st.camera_input("開啟相機拍照")
    uploaded = st.file_uploader("或從相簿選擇照片", type=["jpg", "jpeg", "png"])
    image_file = photo or uploaded

with col_preview:
    if image_file:
        img = Image.open(image_file)
        st.image(img, caption="餐點照片", use_container_width=True)
        analyze_btn = st.button("🚀 開始分析這餐熱量", type="primary", use_container_width=True)
    else:
        st.info("請於左側開啟相機拍照或選擇檔案。")
        analyze_btn = False

if image_file and analyze_btn:
    with st.spinner("AI 正在解析食材與估算營養份量..."):
        try:
            prompt = (
                "你是一位專業營養師。請詳細分析照片中的餐點，拆解每項食材、估計重量/份量，"
                "並計算熱量、蛋白質、碳水化合物、脂肪。最後給出適合減重期的飲食評價。"
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[img, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MealAnalysis,
                    temperature=0.2,
                )
            )
            result: MealAnalysis = response.parsed

            # 加入 session_state 紀錄
            new_meal_items = [{
                "食物名稱": item.name,
                "份量": item.portion,
                "熱量 (kcal)": item.calories,
                "蛋白質 (g)": item.protein,
                "碳水 (g)": item.carbs,
                "脂肪 (g)": item.fat
            } for item in result.items]

            st.session_state.meals_log.append({
                "meal_type": result.meal_type,
                "items": new_meal_items,
                "advice": result.health_advice
            })

            st.success("記錄完成！上方儀表板已更新。")
            st.rerun()

        except Exception as e:
            st.error(f"分析失敗：{e}")

# 7. 今日飲食日誌清單
if st.session_state.meals_log:
    st.subheader("📋 今日已記錄餐點")
    for idx, meal in enumerate(st.session_state.meals_log):
        with st.expander(f"餐點 #{idx+1} ({meal['meal_type']}) - 總計 {sum(x['熱量 (kcal)'] for x in meal['items']):.0f} kcal", expanded=True):
            df_meal = pd.DataFrame(meal["items"])
            st.dataframe(df_meal, use_container_width=True)
            st.caption(f"💡 營養師建議：{meal['advice']}")
            
    if st.button("清空今日記錄"):
        st.session_state.meals_log = []
        st.rerun()
