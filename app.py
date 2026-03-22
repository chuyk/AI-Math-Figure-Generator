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
    
    # API Key 輸入與清除機制
    if "api_key" not in st.session_state:
        st.session_state.api_key = ""

    api_key_input = st.text_input("請輸入 Google AI API Key", type="password", value=st.session_state.api_key)
    
    if api_key_input != st.session_state.api_key:
         st.session_state.api_key = api_key_input

    if st.button("🗑️ 清除 API Key"):
        st.session_state.api_key = ""
        st.rerun()

    # 檢核碼
    passcode = st.text_input("請輸入檢核碼", type="password")

    # 模型選擇 (已移除沒有免費額度的 Pro 模型)
    model_mapping = {
        "Gemini 3.1 Flash-Lite": "gemini-3.1-flash-lite-preview",
        "Gemini 3 Flash": "gemini-3-flash-preview"
    }
    selected_model_display = st.selectbox(
        "選擇 AI 模型",
        options=list(model_mapping.keys()),
        index=0 
    )
    selected_model = model_mapping[selected_model_display]

    # 輸出格式選擇
    output_format = st.radio("選擇圖片輸出格式", ["svg", "png"], index=0)

# ---------------- 主畫面：題目輸入與預覽區 ----------------
# 檢核碼驗證
if passcode not in ["kai", "kaishow"]:
    if passcode != "":
        st.error("❌ 檢核碼不正確，無法執行程式。")
    st.stop()

st.success("✅ 授權通過！")

col1, col2 = st.columns([1, 1])

# --- 左側：輸入區 ---
with col1:
    st.subheader("📝 輸入題目")
    problem_text = st.text_area("請貼上題目 (支援 Markdown 或 LaTeX 語法)", height=150, 
                                placeholder="例如：正方形 ABCD 中，F 是 CD 中點...")
    
    st.subheader("🖼️ 或提供題目圖片")
    
    # 加入明顯的虛線框視覺提示
    st.markdown("""
        <style>
        .paste-zone {
            border: 2px dashed #4CAF50;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            background-color: #f1f8e9;
            color: #2e7d32;
            margin-bottom: 10px;
            cursor: pointer;
        }
        </style>
        <div class="paste-zone">
            🖱️ <b>小技巧：請用滑鼠點擊此虛線框內部任意處</b><br>然後直接按下 <code>Ctrl + V</code> 即可貼上剪貼簿的圖片！
        </div>
        """, unsafe_allow_html=True)
        
    uploaded_image = st.file_uploader("或點擊下方按鈕上傳檔案", type=["jpg", "jpeg", "png"])
    
    st.markdown("<br>", unsafe_allow_html=True)
    generate_btn = st.button("🚀 開始產生幾何圖形", type="primary", use_container_width=True)

# --- 右側：預覽與結果區 ---
with col2:
    st.subheader("👀 預覽與結果區")
    if problem_text:
        st.markdown("**【題目預覽】**")
        st.markdown(problem_text)
    if uploaded_image:
        st.image(uploaded_image, caption="已讀取的圖片", use_container_width=True)
    
    st.markdown("---")
    result_container = st.container()

# ---------------- 執行與畫圖邏輯 ----------------
if generate_btn:
    if not st.session_state.api_key:
        st.warning("⚠️ 請先在左側設定區輸入 API Key。")
        st.stop()
        
    if not problem_text and not uploaded_image:
        st.warning("⚠️ 請輸入題目文字或提供題目圖片。")
        st.stop()

    with result_container:
        with st.spinner(f"正在使用 {selected_model_display} 進行邏輯推理與寫程式..."):
            try:
                client = genai.Client(api_key=st.session_state.api_key)
                
                system_prompt = f"""
                你是一個專業的 Python 程式設計師與數學老師。你的任務是閱讀數學幾何題目，並寫出一段 Python 程式碼，使用 matplotlib 畫出符合題目描述的正確圖形。
                
                【嚴格限制與要求】
                1. 只輸出可執行的 Python 程式碼，不要有任何解釋文字，不要解答題目。
                2. 必須設定英文字級為 18pt：`plt.rcParams.update({{'font.size': 18}})`。
                3. **畫布設定與防裁切 (極度重要)**：請設定適當的畫布大小 `plt.figure(figsize=(6, 6))`。為了防止 18pt 的文字超出畫布被切掉，請務必計算圖形的 x 和 y 座標範圍，並使用 `ax.set_xlim()` 和 `ax.set_ylim()` 在上下左右各多保留 **至少 1.5 到 2 個單位** 的空白 padding。
                4. 所有頂點必須有清晰的英文標示，標示文字的座標需加上微小的位移 (offset)，避免與線條或頂點重疊。
                5. 題目中提到的已知長度必須標示在圖形上的對應位置。
                6. 必須隱藏座標軸：`plt.axis('off')`。
                7. 結束前請加上 `plt.tight_layout()`，最後將圖片儲存為檔案：`plt.savefig('output.{output_format}', format='{output_format}', bbox_inches='tight', pad_inches=0.3)`，不要呼叫 `plt.show()`。
                """
                
                contents = [system_prompt]
                if problem_text:
                    contents.append(f"題目文字：\n{problem_text}")
                if uploaded_image:
                    image_part = types.Part.from_bytes(data=uploaded_image.getvalue(), mime_type=uploaded_image.type)
                    contents.append(image_part)

                response = client.models.generate_content(
                    model=selected_model,
                    contents=contents
                )
                
                response_text = response.text
                code_match = re.search(r'```python\n(.*?)\n```', response_text, re.DOTALL)
                
                if code_match:
                    python_code = code_match.group(1)
                    
                    exec(python_code)
                    
                    st.success("🎉 圖形繪製成功！")
                    
                    file_path = f"output.{output_format}"
                    if os.path.exists(file_path):
                        st.image(file_path, caption=f"產生的幾何圖形 ({output_format.upper()})", use_container_width=True)
                        
                        with open(file_path, "rb") as file:
                            btn = st.download_button(
                                label=f"💾 下載 {output_format.upper()} 圖片",
                                data=file,
                                file_name=f"geometry_figure.{output_format}",
                                mime=f"image/{output_format}"
                            )
                    
                    if passcode == "kaishow":
                        st.markdown("### 💻 後台繪圖程式碼")
                        st.code(python_code, language="python")
                        
                else:
                    st.error("❌ AI 未能產生有效的 Python 程式碼，請稍後再試或調整題目描述。")
                    if passcode == "kaishow":
                        st.write("AI 原始回應：", response_text)

            except Exception as e:
                st.error(f"執行時發生錯誤：{e}")