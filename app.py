import streamlit as st
from google import genai
from google.genai import types
import re
import os
import matplotlib as mpl
import matplotlib.pyplot as plt
import uuid

# ---------------- 設定頁面與標題 ----------------
st.set_page_config(page_title="AI 數學幾何附圖生成器", page_icon="📐", layout="wide")

st.title("📐 AI 數學幾何附圖生成器")
st.markdown("**👨‍🏫 宜蘭縣中華國中教師 / 阿凱老師製作**")
st.markdown("---")

# ---------------- 初始化 Session State ----------------
if "api_key" not in st.session_state:
    st.session_state.api_key = ""

# Tab 1 狀態
if "generated_img_path" not in st.session_state:
    st.session_state.generated_img_path = None
if "generated_code" not in st.session_state:
    st.session_state.generated_code = None
if "current_format" not in st.session_state:
    st.session_state.current_format = None
if "text_input_ai" not in st.session_state:
    st.session_state.text_input_ai = ""

# Tab 2 狀態
if "manual_img_path" not in st.session_state:
    st.session_state.manual_img_path = None
if "manual_format" not in st.session_state:
    st.session_state.manual_format = None
if "manual_code_input" not in st.session_state:
    st.session_state.manual_code_input = ""

if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = str(uuid.uuid4())

# ---------------- 側邊欄：設定區 ----------------
with st.sidebar:
    st.header("🧹 畫面管理")
    if st.button("✨ 一鍵清除所有輸入與結果", use_container_width=True):
        st.session_state.text_input_ai = ""
        st.session_state.manual_code_input = ""
        st.session_state.uploader_key = str(uuid.uuid4()) 
        st.session_state.generated_img_path = None
        st.session_state.generated_code = None
        st.session_state.manual_img_path = None
        st.rerun()

    st.markdown("---")
    st.header("⚙️ 系統設定")
    
    api_key_input = st.text_input("請輸入 Google AI API Key", type="password", value=st.session_state.api_key)
    if api_key_input != st.session_state.api_key:
         st.session_state.api_key = api_key_input

    if st.button("🗑️ 清除 API Key"):
        st.session_state.api_key = ""
        st.session_state.generated_img_path = None
        st.session_state.generated_code = None
        st.session_state.manual_img_path = None
        st.rerun()

    passcode = st.text_input("請輸入檢核碼", type="password")

    model_mapping = {
        "Gemini 3.1 Flash-Lite": "gemini-3.1-flash-lite-preview",
        "Gemini 3 Flash": "gemini-3-flash-preview"
    }
    selected_model_display = st.selectbox("選擇 AI 模型", options=list(model_mapping.keys()), index=1)
    selected_model = model_mapping[selected_model_display]

    output_format = st.radio("選擇圖片輸出格式", ["svg", "png"], index=0)
    is_transparent = st.checkbox("💡 生成透明背景圖形 (去背)", value=True)
    is_curved_label = st.checkbox("💡 長度數字兩側加上標示曲線 (無箭號)", value=False)
    is_text_masking = st.checkbox("💡 長度數字旁留出空白區 (Mask)", value=True)
    
    # 【新增功能】1/5 標線選項
    is_short_dim_label = st.checkbox("💡 長度標示線縮短為 1/5 段長 (無箭號)", value=False)
    
    st.markdown("---")
    text_render_mode = st.radio(
        "🔤 文字渲染模式 (Word 相容性)",
        options=["純 Unicode (推薦，Word 轉換不破碎)", "LaTeX 數學語法 (較美觀，但 Word 轉換會碎裂)"],
        index=0
    )
    is_latex_mode = text_render_mode.startswith("LaTeX")

# ---------------- 檢核碼驗證 ----------------
if passcode not in ["kai", "kaishow"]:
    if passcode != "":
        st.error("❌ 檢核碼不正確，無法執行程式。")
    st.stop()

st.success("✅ 授權通過！")

# ---------------- 動態產生提示詞輔助字串 ----------------
# 1. 曲線指令
curve_instruction = ""
if is_curved_label:
    curve_instruction = "\n8. 【標示曲線要求】：標示長度時，請使用 `ax.annotate('', xy=端點1, xytext=端點2, arrowprops=dict(arrowstyle='-', connectionstyle='arc3,rad=0.2', color='black'))` 來精準連接線段兩端點，不要連到文字中心。"

# 2. LaTeX/Unicode 指令
if is_latex_mode:
    latex_instruction = "5. 頂點與長度標示：允許使用 LaTeX 語法 (如 `$\\angle A = 30^\\circ$` 或 `$2\\sqrt{3}$`) 來確保數學符號美觀。"
else:
    latex_instruction = "5. 頂點與長度標示：【防碎裂極度重要】絕對禁止使用 LaTeX 語法 (如 `$\\angle A = 30^\\circ$` 或 `$2\\sqrt{3}$`)，請一律使用「純 Unicode 文字」(如 `'∠A=30°'`)，避免 SVG 匯入 Word 時文字碎裂。"

# 3. 文字遮罩指令 (防線條穿透文字)
mask_instruction = ""
if is_text_masking:
    mask_instruction = "\n9. 【文字遮罩要求 (防線條穿透)】：輸出數字或標示文字的 `text` 或 `annotate` 必須加上白色遮罩參數：`bbox=dict(fc='white', ec='none', pad=0.1)`，確保壓在底下的線條被擋住。"

# 4. 1/5 標線指令 (動態計算)
short_dim_instruction = ""
if is_short_dim_label:
    short_dim_instruction = "\n10. 【長度標示線縮短要求 (極度重要)】：使用者要求長度數字旁必須有「1/5 標線」。標示線段 (p1, p2) 長度時，不要繪製一條完整的連線。請分別繪製從 p1 到 p1+0.2*(p2-p1)，以及從 p2 到 p2-0.2*(p2-p1) 的短線 (例如使用 `ax.plot` 繪製向量 L*0.2)。兩段短線中間留白，標示數字或問號放中間。嚴禁畫箭頭。"

# ---------------- 共用畫圖存檔函式 ----------------
def execute_and_save_plot(python_code, file_format, transparent):
    try:
        plt.close('all') 
        safe_code = re.sub(r'plt\.show\(\)', '', python_code)
        mpl.rcParams['svg.fonttype'] = 'none'
        
        exec(safe_code, globals())
        fig = plt.gcf()
        
        if not fig.axes:
            raise ValueError("程式碼沒有產生任何有效的 matplotlib 圖形。")
            
        if transparent:
            fig.patch.set_alpha(0.0)
            for ax in fig.axes:
                ax.patch.set_alpha(0.0)
                
        file_path = f"output.{file_format}"
        # 【解決超出畫布】加回 bbox_inches='tight' 和小小的 pad_inches=0.1 作為緩衝區域
        fig.savefig(file_path, format=file_format, bbox_inches='tight', pad_inches=0.1, transparent=transparent, dpi=300)
        return file_path
    except Exception as e:
        raise e

# ---------------- 建立雙頁籤介面 ----------------
tab1, tab2 = st.tabs(["🤖 AI 產生圖形 (根據題目)", "💻 直接執行 Python 程式碼"])

# ================= 頁籤 1：AI 產生圖形 =================
with tab1:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("📝 輸入題目")
        problem_text = st.text_area("請貼上題目 (支援 Markdown 或 LaTeX 語法)", height=150, 
                                    placeholder="例如：正方形 ABCD 中，F 是 CD 中點...", key="text_input_ai")
        
        st.subheader("🖼️ 或提供題目圖片")
        uploaded_image = st.file_uploader("點擊上傳或拖曳圖片檔案", type=["jpg", "jpeg", "png"], key=st.session_state.uploader_key)
        
        st.markdown("<br>", unsafe_allow_html=True)
        generate_btn = st.button("🚀 開始產生幾何圖形", type="primary", use_container_width=True)

    with col2:
        st.subheader("👀 預覽與結果區")
        result_container_ai = st.container()

        if generate_btn:
            if not st.session_state.api_key:
                st.warning("⚠️ 請先在左側設定區輸入 API Key。")
                st.stop()
            if not problem_text and not uploaded_image:
                st.warning("⚠️ 請輸入題目文字或提供題目圖片。")
                st.stop()

            with result_container_ai:
                with st.spinner(f"正在使用 {selected_model_display} 進行邏輯推理與寫程式..."):
                    try:
                        client = genai.Client(api_key=st.session_state.api_key)
                        
                        system_prompt = f"""
                        你是一個專業的 Python 程式設計師與數學老師。任務：閱讀幾何題目，寫出 matplotlib 畫圖 Python 程式碼。
                        
                        【嚴格限制與防裁切要求】
                        1. 務必將程式碼包裝在三個反引號(backticks)中。不要解釋，不要解答。
                        2. 開頭加入 `import matplotlib as mpl` 與 `mpl.rcParams['svg.fonttype'] = 'none'`。
                        3. 設定字級：`plt.rcParams.update({{'font.size': 18}})`。
                        4. 畫布大小 `plt.figure(figsize=(6, 6))`。使用 `ax.set_xlim()` 和 `ax.set_ylim()` 在上下左右各保留 **至少 1.0 個單位** 的空白 padding 區域以防止裁切（尤其是較大的字體或標示）。不要留太少。
                        {latex_instruction}
                        6. 【極度重要】附圖只能畫出題目中給定的「已知條件」，絕對不可以畫出要求解的「答案」或輔助線！
                        7. 隱藏座標軸：`plt.axis('off')`。{curve_instruction}{mask_instruction}{short_dim_instruction}
                        """
                        
                        contents = [system_prompt]
                        if problem_text: contents.append(f"題目文字：\n{problem_text}")
                        if uploaded_image:
                            image_part = types.Part.from_bytes(data=uploaded_image.getvalue(), mime_type=uploaded_image.type)
                            contents.append(image_part)

                        response = client.models.generate_content(model=selected_model, contents=contents)
                        response_text = response.text
                        
                        marker = chr(96) * 3
                        pattern = rf"{marker}(?:python)?\n(.*?)\n{marker}"
                        code_match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
                        
                        if code_match:
                            python_code = code_match.group(1)
                        elif "import matplotlib" in response_text:
                            python_code = response_text.replace(f'{marker}python', '').replace(marker, '').strip()
                        else:
                            raise ValueError("無法從 AI 回應中解析出 Python 程式碼。")

                        file_path = execute_and_save_plot(python_code, output_format, is_transparent)
                        
                        st.session_state.generated_img_path = file_path
                        st.session_state.generated_code = python_code
                        st.session_state.current_format = output_format
                        st.success("🎉 圖形繪製成功！")

                    except Exception as e:
                        st.error(f"❌ 發生錯誤：{e}")
                        if passcode == "kaishow":
                            st.write("AI 原始回應片段：", response_text[:500] + "...")

        if st.session_state.generated_img_path and os.path.exists(st.session_state.generated_img_path):
            with result_container_ai:
                st.image(st.session_state.generated_img_path, caption=f"幾何圖形 ({st.session_state.current_format.upper()})", use_container_width=True)
                with open(st.session_state.generated_img_path, "rb") as file:
                    st.download_button(
                        label=f"💾 下載 {st.session_state.current_format.upper()} 圖片",
                        data=file, file_name=f"geometry_figure.{st.session_state.current_format}",
                        mime=f"image/{st.session_state.current_format}", key="download_ai"
                    )
                if passcode == "kaishow" and st.session_state.generated_code:
                    st.markdown("### 💻 後台繪圖程式碼")
                    st.code(st.session_state.generated_code, language="python")

# ================= 頁籤 2：直接執行 Python 程式碼 =================
with tab2:
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.subheader("📋 產生繪圖程式碼專用提詞 (Prompt)")
        st.info("💡 將下方提詞與您的題目一起貼給 ChatGPT / Claude，請它們幫您寫出最相容的 Python 程式碼！")
        
        prompt_template = f"""你是一個專業的 Python 程式設計師與數學老師。任務：閱讀幾何題目，寫出 matplotlib 畫圖 Python 程式碼。
【嚴格限制與防裁切要求】
1. 務必將程式碼包裝在三個反引號中。不要解釋，不要解答。
2. 開頭加入 `import matplotlib as mpl` 與 `mpl.rcParams['svg.fonttype'] = 'none'`。
3. 設定字級：`plt.rcParams.update({{'font.size': 18}})`。
4. 畫布大小 `plt.figure(figsize=(6, 6))`。使用 `ax.set_xlim()` 和 `ax.set_ylim()` 在上下左右各保留 **至少 1.0 個單位** 的空白 padding 區域以防止裁切。不要留太少。
{latex_instruction}
6. 只標示題目中給定的「已知條件」，絕對不可以畫出要求解的「答案」！
7. 隱藏座標軸：`plt.axis('off')`。{curve_instruction}{mask_instruction}{short_dim_instruction}"""
        
        st.code(prompt_template, language="markdown")
        
        st.subheader("💻 貼上您的 Python 程式碼")
        manual_code = st.text_area("在此貼上 Python 程式碼", height=250, placeholder="import matplotlib.pyplot as plt\n...", key="manual_code_input")
        execute_btn = st.button("⚡ 執行程式碼並產出圖形", type="primary", use_container_width=True)
    
    with col_right:
        st.subheader("👀 預覽與結果區")
        result_container_manual = st.container()
        
        if execute_btn:
            if not manual_code.strip():
                st.warning("⚠️ 請先貼上程式碼。")
            else:
                with result_container_manual:
                    with st.spinner("正在執行程式碼..."):
                        try:
                            file_path = execute_and_save_plot(manual_code, output_format, is_transparent)
                            
                            st.session_state.manual_img_path = file_path
                            st.session_state.manual_format = output_format
                            st.success("🎉 圖形繪製成功！")
                            
                        except Exception as e:
                            st.error(f"❌ 程式碼執行錯誤：{e}")
        
        if st.session_state.manual_img_path and os.path.exists(st.session_state.manual_img_path):
            with result_container_manual:
                st.image(st.session_state.manual_img_path, caption=f"手動產生的圖形 ({st.session_state.manual_format.upper()})", use_container_width=True)
                with open(st.session_state.manual_img_path, "rb") as file:
                    st.download_button(
                        label=f"💾 下載 {st.session_state.manual_format.upper()} 圖片",
                        data=file, file_name=f"manual_geometry_figure.{st.session_state.manual_format}",
                        mime=f"image/{st.session_state.manual_format}", key="download_manual_btn"
                    )