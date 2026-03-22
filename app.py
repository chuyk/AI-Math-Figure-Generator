import streamlit as st
from google import genai
from google.genai import types
import re
import os
import matplotlib.pyplot as plt

# ---------------- 設定頁面與標題 ----------------
st.set_page_config(page_title="AI 數學幾何附圖生成器", page_icon="📐", layout="wide")

st.title("📐 AI 數學幾何附圖生成器")
st.markdown("**👨‍🏫 宜蘭縣中華國中教師 / 阿凱老師製作**")
st.markdown("---")

# ---------------- 側邊欄：設定區 ----------------
with st.sidebar:
    st.header("⚙️ 系統設定")
    
    # 1. API Key 輸入與清除機制 (使用 Session State 模擬暫存)
    if "api_key" not in st.session_state:
        st.session_state.api_key = ""

    api_key_input = st.text_input("請輸入 Google AI API Key", type="password", value=st.session_state.api_key)
    
    if api_key_input != st.session_state.api_key:
         st.session_state.api_key = api_key_input

    if st.button("🗑️ 清除 API Key"):
        st.session_state.api_key = ""
        st.rerun()

    # 2. 檢核碼
    passcode = st.text_input("請輸入檢核碼", type="password")

    # 3. 模型選擇
    model_mapping = {
        "Gemini 3.1 Flash-Lite": "gemini-3.1-flash-lite", # 依據未來實際 API 名稱可能需微調
        "Gemini 3 Flash": "gemini-3-flash",
        "Gemini 3.1 Pro": "gemini-3.1-pro"
    }
    selected_model_display = st.selectbox(
        "選擇 AI 模型",
        options=list(model_mapping.keys()),
        index=0 # 預設為第一個 (Flash-Lite)
    )
    selected_model = model_mapping[selected_model_display]

    # 4. 輸出格式選擇
    output_format = st.radio("選擇圖片輸出格式", ["svg", "png"], index=0)

# ---------------- 主畫面：題目輸入區 ----------------
# 檢核碼驗證
if passcode not in ["kai", "kaishow"]:
    if passcode != "":
        st.error("❌ 檢核碼不正確，無法執行程式。")
    st.stop() # 停止執行下方程式碼

st.success("✅ 授權通過！")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📝 輸入題目")
    problem_text = st.text_area("請貼上題目 (支援 Markdown 或 LaTeX 語法)", height=200, 
                                placeholder="例如：正方形 ABCD 中，F 是 CD 中點...")
    
    st.subheader("🖼️ 或上傳題目圖片")
    uploaded_image = st.file_uploader("上傳圖片檔案", type=["jpg", "jpeg", "png"])

with col2:
    st.subheader("預覽區")
    if problem_text:
        st.markdown(" **題目預覽：** ")
        st.markdown(problem_text)
    if uploaded_image:
        st.image(uploaded_image, caption="已上傳的圖片", use_container_width=True)

# ---------------- 執行與畫圖邏輯 ----------------
if st.button("🚀 開始產生幾何圖形", type="primary"):
    if not st.session_state.api_key:
        st.warning("⚠️ 請先在左側設定區輸入 API Key。")
        st.stop()
        
    if not problem_text and not uploaded_image:
        st.warning("⚠️ 請輸入題目文字或上傳題目圖片。")
        st.stop()

    with st.spinner(f"正在使用 {selected_model_display} 進行邏輯推理與寫程式..."):
        try:
            # 初始化 Client
            client = genai.Client(api_key=st.session_state.api_key)
            
            # 準備給 AI 的 Prompt
            system_prompt = f"""
            你是一個專業的 Python 程式設計師與數學老師。你的任務是閱讀數學幾何題目，並寫出一段 Python 程式碼，使用 matplotlib 畫出符合題目描述的正確圖形。
            
            【嚴格限制與要求】
            1. 只輸出可執行的 Python 程式碼，不要有任何解釋文字，不要解答題目。
            2. 必須設定英文字級為 18pt：`plt.rcParams.update({{'font.size': 18}})`。
            3. 所有頂點必須有清晰的英文標示。
            4. 題目中提到的已知長度必須標示在圖形上的對應位置。
            5. 必須隱藏座標軸：`plt.axis('off')`。
            6. 最後必須將圖片儲存為檔案：`plt.savefig('output.{output_format}', format='{output_format}', bbox_inches='tight')`，不要呼叫 `plt.show()`。
            """
            
            contents = [system_prompt]
            if problem_text:
                contents.append(f"題目文字：\n{problem_text}")
            if uploaded_image:
                # 將上傳的圖片轉為 API 可接受的格式
                image_part = types.Part.from_bytes(data=uploaded_image.getvalue(), mime_type=uploaded_image.type)
                contents.append(image_part)

            # 呼叫 Gemini API
            response = client.models.generate_content(
                model=selected_model,
                contents=contents
            )
            
            # 提取 Python 程式碼
            response_text = response.text
            code_match = re.search(r'```python\n(.*?)\n```', response_text, re.DOTALL)
            
            if code_match:
                python_code = code_match.group(1)
                
                # 執行 Python 程式碼產生圖片
                exec(python_code)
                
                # 顯示產生的圖片
                st.success("🎉 圖形繪製成功！")
                
                file_path = f"output.{output_format}"
                if os.path.exists(file_path):
                    st.image(file_path, caption=f"產生的幾何圖形 ({output_format.upper()})", use_container_width=True)
                    
                    # 提供下載按鈕
                    with open(file_path, "rb") as file:
                        btn = st.download_button(
                            label=f"💾 下載 {output_format.upper()} 圖片",
                            data=file,
                            file_name=f"geometry_figure.{output_format}",
                            mime=f"image/{output_format}"
                        )
                
                # 如果檢核碼是 kaishow，顯示程式碼
                if passcode == "kaishow":
                    st.markdown("### 💻 後台繪圖程式碼 (供複製至 Colab)")
                    st.code(python_code, language="python")
                    
            else:
                st.error("❌ AI 未能產生有效的 Python 程式碼，請稍後再試或調整題目描述。")
                if passcode == "kaishow":
                    st.write("AI 原始回應：", response_text)

        except Exception as e:
            st.error(f"執行時發生錯誤：{e}")