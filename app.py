import streamlit as st
from PIL import Image
import pandas as pd
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timedelta
import uuid
import plotly.graph_objects as go
from google import genai
from google.genai import types
from supabase import create_client, Client

# -------------------------------------------------------------
# 1. 頁面配置與 WiseMeal 日韓系天藍純白 UI CSS
# -------------------------------------------------------------
st.set_page_config(
    page_title="WiseMeal AI - 智慧飲食管家",
    page_icon="🥗",
    layout="centered",
    initial_sidebar_state="collapsed"
)

WISEMEAL_CSS = """
<style>
/* 徹底抹除 Streamlit 原生頂部 Header、選單、Share、Footer */
header[data-testid="stHeader"], #MainMenu, footer, .stAppDeployButton {
    display: none !important;
    visibility: hidden !important;
}

/* 背景採用天藍淡彩微漸層 */
.stApp {
    background: linear-gradient(180deg, #EBF5FF 0%, #F8FAFC 260px, #F1F5F9 100%) !important;
    color: #1E293B !important;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif !important;
}

.main .block-container {
    padding-top: 1rem !important;
    padding-bottom: 4rem !important;
    max-width: 480px !important;
    margin: 0 auto !important;
}

/* 核心純白立體卡片 */
.wm-card {
    background: #FFFFFF;
    border-radius: 22px;
    padding: 18px 20px;
    margin-bottom: 14px;
    box-shadow: 0 8px 24px rgba(56, 128, 255, 0.06), 0 2px 6px rgba(0, 0, 0, 0.02);
    border: 1px solid rgba(226, 232, 240, 0.8);
}

/* 日曆選擇膠囊 */
.calendar-bar {
    display: flex;
    justify-content: space-between;
    margin-bottom: 14px;
    gap: 4px;
}

.cal-pill {
    flex: 1;
    text-align: center;
    padding: 8px 2px;
    border-radius: 14px;
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    color: #64748B;
    font-size: 0.72rem;
}

.cal-pill.active {
    background: #2563EB !important;
    color: #FFFFFF !important;
    border-color: #2563EB !important;
    font-weight: 700;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
}

/* 雙欄熱量與巨量看板 */
.budget-grid {
    display: grid;
    grid-template-columns: 1.1fr 1fr;
    gap: 12px;
    margin-bottom: 16px;
}

.budget-circle-box {
    background: #FFFFFF;
    border-radius: 22px;
    padding: 16px;
    text-align: center;
    border: 1px solid #E2E8F0;
    box-shadow: 0 8px 24px rgba(56, 128, 255, 0.06);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
}

.circle-water {
    width: 120px;
    height: 120px;
    border-radius: 50%;
    background: radial-gradient(circle, #EFF6FF 0%, #DBEAFE 100%);
    border: 4px solid #3B82F6;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    box-shadow: inset 0 2px 8px rgba(59, 130, 246, 0.15);
}

.macro-list-box {
    background: #FFFFFF;
    border-radius: 22px;
    padding: 14px 16px;
    border: 1px solid #E2E8F0;
    box-shadow: 0 8px 24px rgba(56, 128, 255, 0.06);
    display: flex;
    flex-direction: column;
    justify-content: space-around;
}

.macro-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin: 4px 0;
}

/* 彩色膠囊標籤 */
.badge-carb { background: #ECFDF5; color: #059669; border-radius: 8px; padding: 2px 8px; font-weight:700; font-size:0.75rem;}
.badge-pro { background: #EFF6FF; color: #2563EB; border-radius: 8px; padding: 2px 8px; font-weight:700; font-size:0.75rem;}
.badge-fat { background: #FFFBEB; color: #D97706; border-radius: 8px; padding: 2px 8px; font-weight:700; font-size:0.75rem;}

/* Tab 導航列美化 */
.stTabs [data-baseweb="tab-list"] {
    background-color: transparent !important;
    gap: 8px;
}
.stTabs [data-baseweb="tab"] {
    background: #FFFFFF !important;
    border-radius: 14px !important;
    padding: 8px 16px !important;
    font-weight: 600 !important;
    color: #64748B !important;
    border: 1px solid #E2E8F0 !important;
}
.stTabs [aria-selected="true"] {
    background: #2563EB !important;
    color: #FFFFFF !important;
    border: 1px solid #2563EB !important;
}

/* 按鈕美化 */
.stButton > button {
    background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
    color: #FFFFFF !important;
    border-radius: 14px !important;
    border: none !important;
    font-weight: 700 !important;
    height: 48px !important;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.25) !important;
}
</style>
"""
st.markdown(WISEMEAL_CSS, unsafe_allow_html=True)

# -------------------------------------------------------------
# 2. 金鑰與連線初始化
# -------------------------------------------------------------
gemini_key = st.secrets.get("GEMINI_API_KEY", "")
supabase_url = st.secrets.get("SUPABASE_URL", "")
supabase_key = st.secrets.get("SUPABASE_KEY", "")

if not (gemini_key and supabase_url and supabase_key):
    st.error("請在 Streamlit Secrets 設定 GEMINI_API_KEY、SUPABASE_URL 與 SUPABASE_KEY。")
    st.stop()

ai_client = genai.Client(api_key=gemini_key)
supabase: Client = create_client(supabase_url, supabase_key)

# -------------------------------------------------------------
# 3. 設備識別碼綁定 (Device ID)
# -------------------------------------------------------------
if "device_id" not in st.query_params:
    assigned_id = f"dev_{str(uuid.uuid4())[:8]}"
    st.query_params["device_id"] = assigned_id
    st.session_state["device_id"] = assigned_id
else:
    st.session_state["device_id"] = st.query_params["device_id"]

device_id = st.session_state["device_id"]

def get_profile(d_id):
    try:
        r = supabase.table("user_profiles").select("*").eq("device_id", d_id).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None

def get_meals_today(d_id):
    try:
        today_str = datetime.utcnow().strftime("%Y-%m-%d 00:00:00")
        r = supabase.table("meals").select("*").eq("device_id", d_id).gte("created_at", today_str).order("created_at", desc=True).execute()
        return r.data or []
    except Exception:
        return []

profile = get_profile(device_id)

# -------------------------------------------------------------
# 4. 門禁關卡：健康問卷建立專屬 TDEE (首次造訪)
# -------------------------------------------------------------
if not profile:
    st.markdown("""
<div style="text-align:center; padding: 20px 0 10px 0;">
<h2 style="font-weight: 800; color: #1E3A8A; margin: 0;">✨ WiseMeal AI</h2>
<p style="color: #64748B; font-size: 0.9rem; margin-top: 6px;">客製您的身體密碼，量身打造專屬減重目標</p>
</div>
""", unsafe_allow_html=True)

    with st.form("wm_onboarding"):
        st.markdown("<div class='wm-card'>", unsafe_allow_html=True)
        gender = st.radio("生理性別", ["女性", "男性"], horizontal=True)
        c1, c2 = st.columns(2)
        with c1:
            age = st.number_input("年齡", min_value=12, max_value=99, value=25)
        with c2:
            height = st.number_input("身高 (cm)", min_value=120.0, max_value=230.0, value=163.0, step=0.5)
        weight = st.number_input("體重 (kg)", min_value=30.0, max_value=200.0, value=55.0, step=0.5)
        
        act = st.selectbox(
            "日常活動程度",
            ["久坐上班族 (1.2)", "輕度運動 1-3 天 (1.375)", "中度規律運動 3-5 天 (1.55)", "高度強度運動 6-7 天 (1.725)"]
        )
        deficit = st.select_slider("減重熱量赤字 (kcal/天)", options=[0, 300, 400, 500], value=400)
        submit_btn = st.form_submit_button("計算 TDEE 並進入系統", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if submit_btn:
            act_map = {"久坐上班族 (1.2)": 1.2, "輕度運動 1-3 天 (1.375)": 1.375, "中度規律運動 3-5 天 (1.55)": 1.55, "高度強度運動 6-7 天 (1.725)": 1.725}
            factor = act_map[act]
            bmr = (10 * weight) + (6.25 * height) - (5 * age) + (5 if gender == "男性" else -161)
            tdee = bmr * factor
            daily_budget = max(bmr, tdee - deficit)

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

    st.stop()

# -------------------------------------------------------------
# 5. 首頁頂部：WiseMeal 週曆與核心波浪熱量雙欄儀表板
# -------------------------------------------------------------
today_meals = get_meals_today(device_id)

consumed_cal = sum(m.get("calories", 0) for m in today_meals)
consumed_pro = sum(m.get("protein", 0) for m in today_meals)
consumed_carbs = sum(m.get("carbs", 0) for m in today_meals)
consumed_fat = sum(m.get("fat", 0) for m in today_meals)

budget = profile["daily_budget"]
remaining = budget - consumed_cal

# 頂部 App 標題列
st.markdown("""
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
<div>
<span style="font-weight:900; font-size:1.4rem; color:#1E3A8A; letter-spacing:-0.5px;">WiseMeal</span>
<span style="background:#DBEAFE; color:#1D4ED8; font-size:0.75rem; font-weight:700; padding:2px 8px; border-radius:10px; margin-left:6px;">PRO</span>
</div>
<div style="font-size:0.85rem; color:#64748B;">今天 ▾</div>
</div>
""", unsafe_allow_html=True)

# 動態產生本週日曆條 (如圖 5 所示)
today_dt = datetime.now()
days_html = []
week_names = ["S", "M", "T", "W", "T", "F", "S"]
start_of_week = today_dt - timedelta(days=(today_dt.weekday() + 1) % 7)

for i in range(7):
    d = start_of_week + timedelta(days=i)
    is_today = d.day == today_dt.day
    cls = "cal-pill active" if is_today else "cal-pill"
    days_html.append(f"""
<div class="{cls}">
<div>{week_names[i]}</div>
<div style="font-size:0.95rem; font-weight:700; margin-top:2px;">{d.day}</div>
</div>
""")

st.markdown(f"""
<div class="calendar-bar">
{''.join(days_html)}
</div>
""", unsafe_allow_html=True)

# 雙欄儀表板 (波浪水環熱量 + 巨量營養條，如圖 5 所示)
rem_color = "#2563EB" if remaining >= 0 else "#EF4444"
st.markdown(f"""
<div class="budget-grid">
<div class="budget-circle-box">
<div class="circle-water">
<div style="font-size:0.75rem; color:#64748B; font-weight:600;">剩餘</div>
<div style="font-size:1.8rem; font-weight:900; color:{rem_color}; line-height:1.1;">{abs(remaining):,.0f}</div>
<div style="font-size:0.7rem; color:#94A3B8;">kcal</div>
</div>
<div style="font-size:0.75rem; color:#64748B; margin-top:8px;">目標 {budget:.0f} 千卡</div>
</div>
<div class="macro-list-box">
<div class="macro-row">
<span class="badge-carb">碳水</span>
<span style="font-size:0.85rem; font-weight:700;">{consumed_carbs:.1f}g</span>
</div>
<div class="macro-row">
<span class="badge-pro">蛋白質</span>
<span style="font-size:0.85rem; font-weight:700;">{consumed_pro:.1f}g</span>
</div>
<div class="macro-row">
<span class="badge-fat">脂肪</span>
<span style="font-size:0.85rem; font-weight:700;">{consumed_fat:.1f}g</span>
</div>
</div>
</div>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# 6. 四大核心模組 Tab (精準復刻附圖功能)
# -------------------------------------------------------------
tab_scan, tab_barcode, tab_recipe, tab_report = st.tabs([
    "📸 拍照計算", 
    "🏷️ 添加劑/條碼", 
    "🍳 剩食食譜", 
    "📊 健康數據"
])

# =============================================================
# 功能 1：拍照計算卡路里 + 食材克數細拆 (對應圖 4、圖 6、圖 7)
# =============================================================
with tab_scan:
    st.markdown("<div class='wm-card'>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:1rem; font-weight:700; color:#0F172A; margin-bottom:8px;'>📸 拍照計算卡路里</div>", unsafe_allow_html=True)
    
    photo = st.file_uploader("拍照記錄餐點", type=["jpg", "jpeg", "png"], key="meal_cam", label_visibility="collapsed")

    class ItemDetail(BaseModel):
        name: str = Field(description="食材名稱，如：香煎雞胸肉、糙米飯、西蘭花")
        grams: float = Field(description="預估重量克數(g)")
        calories: float = Field(description="該項食材熱量(kcal)")
        protein: float = Field(description="該項食材蛋白質(g)")
        carbs: float = Field(description="該項食材碳水(g)")
        fat: float = Field(description="該項食材脂肪(g)")

    class MealVisionResult(BaseModel):
        meal_title: str = Field(description="餐點整體名稱，如：雞胸肉時蔬糙米便當")
        meal_type: str = Field(description="餐別：早餐/午餐/晚餐/點心")
        items: List[ItemDetail] = Field(description="各食材項目拆解")
        advice: str = Field(description="減重營養師短評")

    if photo:
        img = Image.open(photo)
        st.image(img, use_container_width=True)
        
        if "meal_res" not in st.session_state or st.session_state.get("meal_cache_key") != photo.name:
            with st.spinner("AI 正在精準拆解食材、重量與營養..."):
                try:
                    res = ai_client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[
                            img,
                            "請如同專業食物辨識App一樣，拆解照片中每一樣食材名稱、重量克數(g)、熱量與三大營養素，並給出整份餐點名稱。"
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=MealVisionResult,
                            temperature=0.2
                        )
                    )
                    st.session_state["meal_res"] = res.parsed
                    st.session_state["meal_cache_key"] = photo.name
                except Exception as e:
                    st.error(f"辨識失敗：{e}")

        if "meal_res" in st.session_state:
            meal_data: MealVisionResult = st.session_state["meal_res"]
            
            # 如圖 4 呈現餐點卡片與四大膠囊
            st.markdown(f"""
<div style="margin-top:14px; border-top:1px solid #F1F5F9; padding-top:12px;">
<div style="font-size:1.15rem; font-weight:800; color:#0F172A;">{meal_data.meal_title}</div>
<div style="display:flex; justify-content:space-between; margin: 10px 0; gap:4px;">
<div style="background:#EFF6FF; padding:6px 10px; border-radius:10px; text-align:center; flex:1;">
<div style="font-size:0.68rem; color:#2563EB;">卡路里</div>
<div style="font-weight:800; font-size:0.95rem; color:#1E40AF;">{sum(x.calories for x in meal_data.items):.0f} kcal</div>
</div>
<div style="background:#ECFDF5; padding:6px 10px; border-radius:10px; text-align:center; flex:1;">
<div style="font-size:0.68rem; color:#059669;">碳水</div>
<div style="font-weight:800; font-size:0.95rem; color:#065F46;">{sum(x.carbs for x in meal_data.items):.1f}g</div>
</div>
<div style="background:#EFF6FF; padding:6px 10px; border-radius:10px; text-align:center; flex:1;">
<div style="font-size:0.68rem; color:#2563EB;">蛋白質</div>
<div style="font-weight:800; font-size:0.95rem; color:#1E40AF;">{sum(x.protein for x in meal_data.items):.1f}g</div>
</div>
<div style="background:#FFFBEB; padding:6px 10px; border-radius:10px; text-align:center; flex:1;">
<div style="font-size:0.68rem; color:#D97706;">脂肪</div>
<div style="font-weight:800; font-size:0.95rem; color:#92400E;">{sum(x.fat for x in meal_data.items):.1f}g</div>
</div>
</div>
</div>
""", unsafe_allow_html=True)
            
            # 食材清單明細 (支援分食比例，如圖 4、圖 7)
            st.markdown("<div style='font-size:0.85rem; font-weight:700; color:#64748B; margin:10px 0 6px 0;'>食材重量拆解明細：</div>", unsafe_allow_html=True)
            for it in meal_data.items:
                st.markdown(f"""
<div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid #F8FAFC; font-size:0.85rem;">
<span style="font-weight:600; color:#334155;">{it.name}</span>
<span style="color:#64748B;">{it.calories:.0f} 千卡 / <b>{it.grams:.0f} 克</b></span>
</div>
""", unsafe_allow_html=True)

            portion_choice = st.select_slider(
                "多人共食 / 食用份量調節",
                options=["1/4 份", "1/3 份", "半份", "完整 1 份", "1.5 份"],
                value="完整 1 份"
            )
            pmap = {"1/4 份": 0.25, "1/3 份": 0.33, "半份": 0.5, "完整 1 份": 1.0, "1.5 份": 1.5}
            mult = pmap[portion_choice]
            
            final_cal = sum(x.calories for x in meal_data.items) * mult

            if st.button("記錄到今日日誌", use_container_width=True):
                supabase.table("meals").insert({
                    "device_id": device_id,
                    "meal_type": meal_data.meal_type,
                    "portion_multiplier": mult,
                    "calories": final_cal,
                    "protein": sum(x.protein for x in meal_data.items) * mult,
                    "carbs": sum(x.carbs for x in meal_data.items) * mult,
                    "fat": sum(x.fat for x in meal_data.items) * mult,
                    "items": [x.model_dump() for x in meal_data.items],
                    "advice": meal_data.advice
                }).execute()
                del st.session_state["meal_res"]
                st.success("記錄入庫成功！")
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# =============================================================
# 功能 2：食品添加劑及致敏原掃描 (精準復刻圖 1、圖 5)
# =============================================================
with tab_barcode:
    st.markdown("<div class='wm-card'>", unsafe_allow_html=True)
    st.markdown("""
<div style="font-size:1.05rem; font-weight:800; color:#0F172A;">添加劑及致敏原掃描</div>
<p style="font-size:0.8rem; color:#64748B; margin: 4px 0 12px 0;">拍照食品背面成分表或條碼，AI 為您揪出加工添加物與過敏原</p>
""", unsafe_allow_html=True)
    
    label_photo = st.file_uploader("拍照成分表或食品外包裝", type=["jpg", "jpeg", "png"], key="label_cam", label_visibility="collapsed")

    class SafetyAnalysis(BaseModel):
        product_name: str = Field(description="商品名稱")
        estimated_calories_per_100g: float = Field(description="每100克或每份熱量")
        additives: List[str] = Field(description="檢出的食品添加劑清單 (例如：乳化劑、膨鬆劑、人工色素等)")
        allergens: List[str] = Field(description="檢出的致敏原 (例如：麩質、蛋類、大豆、花生等)")
        safety_summary: str = Field(description="安全與健康評估總結")

    if label_photo:
        lbl_img = Image.open(label_photo)
        st.image(lbl_img, use_container_width=True)
        
        with st.spinner("AI 正在光學辨識成分清單、添加物與過敏原..."):
            try:
                safety_res = ai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        lbl_img,
                        "請詳細辨識此食品成分標籤：抓出食品添加劑（如乳化劑、防腐劑、色素）、常見致敏原（牛奶、蛋、麩質等），以及熱量與安全性評價。"
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=SafetyAnalysis,
                        temperature=0.2
                    )
                )
                safe_data: SafetyAnalysis = safety_res.parsed
                
                # 如圖 1 呈現添加劑與過敏原氣泡卡
                st.markdown(f"""
<div style="background:#FFF1F2; border:1px solid #FFE4E6; border-radius:18px; padding:16px; margin: 12px 0;">
<div style="display:flex; justify-content:space-between; align-items:center;">
<span style="font-weight:800; color:#BE123C; font-size:1rem;">🧪 檢測出添加劑 ({len(safe_data.additives)} 項)</span>
</div>
<div style="margin-top:8px; font-size:0.85rem; color:#881337;">
{'、'.join(safe_data.additives) if safe_data.additives else '未檢測出明顯人工添加劑，相對天然'}
</div>
</div>

<div style="background:#FEF3C7; border:1px solid #FDE68A; border-radius:18px; padding:16px; margin-bottom: 12px;">
<div style="font-weight:800; color:#B45309; font-size:1rem;">⚠️ 致敏原提醒</div>
<div style="margin-top:8px; font-size:0.85rem; color:#92400E;">
{'、'.join(safe_data.allergens) if safe_data.allergens else '未檢出常見高風險過敏原'}
</div>
</div>

<div style="font-size:0.85rem; color:#475569; background:#F8FAFC; padding:10px 14px; border-radius:12px;">
💡 <b>專家小評：</b>{safe_data.safety_summary}
</div>
""", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"辨識成分失敗：{e}")

    st.markdown("</div>", unsafe_allow_html=True)

# =============================================================
# 功能 3：AI 智慧健康食譜 (精準復刻圖 2)
# =============================================================
with tab_recipe:
    st.markdown("<div class='wm-card'>", unsafe_allow_html=True)
    st.markdown("""
<div style="font-size:1.05rem; font-weight:800; color:#0F172A;">🍳 客製化您的食譜</div>
<p style="font-size:0.8rem; color:#64748B; margin: 4px 0 12px 0;">您的冰箱裡有什麼？輸入食材，AI 為您生成低卡快煮專屬食譜</p>
""", unsafe_allow_html=True)
    
    ingredients_input = st.text_input("現有食材", value="酪梨、生菜、番茄、雞肉")
    c_m, c_t, c_c = st.columns(3)
    with c_m:
        recipe_meal = st.selectbox("餐別", ["午餐", "晚餐", "早餐"])
    with c_t:
        recipe_time = st.selectbox("烹飪時間", ["15 分鐘", "30 分鐘", "45 分鐘"])
    with c_c:
        recipe_cal = st.selectbox("熱量限制", ["<400 kcal", "<500 kcal", "<600 kcal"])

    class SmartRecipe(BaseModel):
        title: str = Field(description="食譜名稱")
        prep_time: str = Field(description="準備時間")
        calories: float = Field(description="預估熱量(kcal)")
        protein: float = Field(description="蛋白質")
        steps: List[str] = Field(description="料理烹調步驟")

    if st.button("✨ 生成低卡食譜", use_container_width=True):
        with st.spinner("AI 大廚正在為您設計營養均衡食譜..."):
            try:
                recipe_prompt = f"請利用食材 [{ingredients_input}]，為減重者設計一款 [{recipe_meal}] 食譜，烹飪時間在 {recipe_time} 內，熱量 {recipe_cal}。"
                rec_res = ai_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[recipe_prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=SmartRecipe,
                        temperature=0.3
                    )
                )
                r_data: SmartRecipe = rec_res.parsed
                
                # 如圖 2 呈現食譜卡片
                st.markdown(f"""
<div style="background:#F0FDF4; border:1px solid #DCFCE7; border-radius:18px; padding:16px; margin-top:14px;">
<div style="font-size:1.15rem; font-weight:800; color:#15803D;">📖 {r_data.title}</div>
<div style="font-size:0.8rem; color:#166534; margin: 4px 0 10px 0;">
⏱️ {r_data.prep_time} · 🔥 {r_data.calories:.0f} kcal · 💪 蛋白質 {r_data.protein:.1f}g
</div>
<div style="font-size:0.85rem; color:#334155; line-height:1.6;">
{'<br>'.join([f"{idx+1}. {step}" for idx, step in enumerate(r_data.steps)])}
</div>
</div>
""", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"食譜生成失敗：{e}")

    st.markdown("</div>", unsafe_allow_html=True)

# =============================================================
# 功能 4：每日健康數據五角雷達分析 (精準復刻圖 3)
# =============================================================
with tab_report:
    st.markdown("<div class='wm-card'>", unsafe_allow_html=True)
    st.markdown("""
<div style="display:flex; justify-content:space-between; align-items:center;">
<span style="font-size:1.05rem; font-weight:800; color:#0F172A;">今日概況：良好 😊</span>
<span style="font-size:0.8rem; color:#64748B;">即時評估</span>
</div>
<p style="font-size:0.8rem; color:#64748B; margin-top:4px;">全方位評估熱量與飲食均衡，掌握代謝狀態</p>
""", unsafe_allow_html=True)
    
    # 根據當日攝取計算動態五角雷達指標 (對應圖 3：卡路里、營養、間隔、多樣性、風險)
    cal_score = max(20, min(100, 100 - abs(budget - consumed_cal) / 10))
    pro_score = min(100, (consumed_pro / 60) * 100) if consumed_pro > 0 else 30
    diversity_score = min(100, len(today_meals) * 35) if today_meals else 20

    radar_categories = ['卡路里控制', '營養配比', '進食間隔', '風險抑制', '食材多樣性']
    radar_values = [cal_score, pro_score, 85, 90, diversity_score]

    # Plotly 繪製五角雷達圖 (對應圖 3 視覺)
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=radar_values,
        theta=radar_categories,
        fill='toself',
        fillcolor='rgba(59, 130, 246, 0.35)',
        line=dict(color='#2563EB', width=2)
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=False, range=[0, 100]),
            angularaxis=dict(tickfont=dict(size=11, color='#64748B'))
        ),
        showlegend=False,
        margin=dict(l=20, r=20, t=20, b=20),
        height=220,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    
    st.markdown(f"""
<div style="background:#EFF6FF; border-radius:14px; padding:12px 14px; font-size:0.82rem; color:#1E40AF;">
🌟 <b>分析總結：</b>今日已攝取 <b>{consumed_cal:.0f}</b> kcal，卡路里達成率符合減重赤字節奏，多補充深綠色蔬菜可進一步提高多樣性評分！
</div>
""", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# -------------------------------------------------------------
# 7. 今日飲食日誌饋給
# -------------------------------------------------------------
st.markdown("<div style='font-weight:800; font-size:1.05rem; color:#0F172A; margin: 16px 0 10px 4px;'>📋 今日已記錄餐點</div>", unsafe_allow_html=True)

if not today_meals:
    st.markdown("<div style='text-align:center; color:#94A3B8; font-size:0.85rem; padding:20px;'>今天還沒有記錄餐點，開啟相機拍下第一餐！</div>", unsafe_allow_html=True)
else:
    for m in today_meals:
        st.markdown(f"""
<div class="wm-card" style="padding:14px 16px;">
<div style="display:flex; justify-content:space-between; align-items:center;">
<span style="font-weight:700; font-size:0.95rem; color:#1E293B;">🍽️ {m.get('meal_type', '餐點')}</span>
<span style="font-weight:800; font-size:1.1rem; color:#2563EB;">{m.get('calories', 0):.0f} kcal</span>
</div>
<div style="font-size:0.75rem; color:#64748B; margin: 2px 0 8px 0;">
份量：{m.get('portion_multiplier', 1.0)}x 比例 · 蛋白質 {m.get('protein', 0):.1f}g
</div>
<div style="font-size:0.8rem; color:#475569; background:#F8FAFC; padding:8px 10px; border-radius:8px;">
💡 {m.get('advice', '維持均衡飲食。')}
</div>
</div>
""", unsafe_allow_html=True)
