import streamlit as st
from PIL import Image
import pandas as pd
from pydantic import BaseModel, Field
from typing import List
from google import genai
from google.genai import types

# 網頁基本設定
st.set_page_config(page_title="AI 拍照熱量日記", page_icon="🥗", layout="centered")

# 1. 取得 API Key (優先從 Streamlit Secrets 讀取)
api_key = st.secrets.get("GEMINI_API_KEY", None)

if not api_key:
    api_key = st.sidebar.text_input("輸入 Gemini API Key", type="password")
    if not api_key:
        st.info("請於側邊欄輸入 Gemini API Key 或設定 Streamlit Secrets 後繼續。")
        st.stop()

# 2. 定義營養結構化輸出格式
class FoodItem(BaseModel):
    name: str = Field(description="食物名稱")
    portion: str = Field(description="預估份量或重量 (例如: 150g, 1碗)")
    calories: float = Field(description="熱量 (kcal)")
    protein: float = Field(description="蛋白質 (g)")
    carbs: float = Field(description="碳水化合物 (g)")
    fat: float = Field(description="脂肪 (g)")

class NutritionAnalysis(BaseModel):
    items: List[FoodItem] = Field(description="餐點內包含的所有食材或項目")
    summary: str = Field(description="整體的營養評價與飲食建議")

# 3. 初始化 Client
client = genai.Client(api_key=api_key)

# 4. 介面視覺
st.title("🥗 AI 拍照熱量與營養分析")
st.write("拍照或上傳餐點照片，AI 自動為您辨識食材並估算熱量與三大營養素。")

# 支援拍照 (手機直接開鏡頭) 或上傳圖片
uploaded_file = st.camera_input("拍照辨識餐點") or st.file_uploader("或選擇圖片檔案", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="已上傳餐點", use_container_width=True)

    if st.button("開始分析營養成分", type="primary"):
        with st.spinner("AI 正在分析餐點份量與熱量..."):
            try:
                # 呼叫 Gemini 進行圖片與結構化輸出分析
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        image,
                        "請詳細辨識照片中的所有食物，預估各食材的重量/份量，並計算其熱量與三大營養素。"
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=NutritionAnalysis,
                        temperature=0.2,
                    ),
                )
                
                # 解析結構化結果
                result: NutritionAnalysis = response.parsed

                # 整理成 DataFrame 顯示
                data = [{
                    "食物項目": item.name,
                    "份量": item.portion,
                    "熱量 (kcal)": item.calories,
                    "蛋白質 (g)": item.protein,
                    "碳水 (g)": item.carbs,
                    "脂肪 (g)": item.fat
                } for item in result.items]
                
                df = pd.DataFrame(data)

                # 計算總和
                total_cal = df["熱量 (kcal)"].sum()
                total_protein = df["蛋白質 (g)"].sum()
                total_carbs = df["碳水 (g)"].sum()
                total_fat = df["脂肪 (g)"].sum()

                st.subheader("📊 營養成分統計")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("總熱量", f"{total_cal:.0f} kcal")
                col2.metric("蛋白質", f"{total_protein:.1f} g")
                col3.metric("碳水化合物", f"{total_carbs:.1f} g")
                col4.metric("脂肪", f"{total_fat:.1f} g")

                st.dataframe(df, use_container_width=True)

                st.subheader("💡 飲食分析與建議")
                st.write(result.summary)

            except Exception as e:
                st.error(f"分析失敗，錯誤訊息：{e}")

# 5. .gitignore 內容防呆提示
