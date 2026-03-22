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

# Tab 2 狀態
if "manual_img_path" not in st.session_state:
    st.session_state.manual_img_path = None
if "manual_format" not in st.session_state:
    st.session_state.manual_format = None

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
    
    api_key_input = st.text_input("請輸入 [Google AI API Key](https://aistudio.google.com/app/api-keys)", type="password", value=st.session_state.api_key)
    if api_key_input != st.session_state.api_key:
         st.session_state.api_key = api_key_input

    if st.button("🗑️ 清除 API Key"):
        st.session_state.api_key = ""
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
    
    st.markdown("---")
    # 【UI 優化】將原本凌亂的 Checkbox 統整為乾淨的單選選單
    dim_style_mapping = {
        "無標線 (僅數字)": "none",
        "完整弧線 (涵蓋全線段)": "full_arc",
        "1/5 短弧線 (僅標示兩端)": "short_arc"
    }
    dim_style_display = st.radio(
        "📏 長度標示線風格",
        options=list(dim_style_mapping.keys()),
        index=2 # 預設為您最想要的 1/5 短弧線
    )
    dim_style = dim_style_mapping[dim_style_display]
    
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
if is_latex_mode:
    latex_instruction = "5. 頂點與長度標示：允許使用 LaTeX 語法 (如 `$\\angle A = 30^\\circ$` 或 `$2\\sqrt{3}$`)。"
else:
    latex_instruction = "5. 頂點與長度標示：【防碎裂極度重要】絕對禁止使用 LaTeX 語法 (如 `$\\angle A = 30^\\circ$`)，請一律使用純 Unicode (如 `'∠A=30°'`)，避免 SVG 匯入 Word 時文字碎裂。"

dim_instruction = f"""
8. 【繪圖專用輔助函式 (極度重要)】：
系統已在背景內建 `draw_dimension(ax, p1, p2, text, mode='{dim_style}', invert=False)` 函式。
- `p1`, `p2`: 線段端點座標 (例如 A, B)
- `text`: 長度數字 (例如 '25')
- `invert`: 弧線預設往外彎。若發現弧線凹進圖形內部，可設為 `True` 反轉。
請「絕對必須」呼叫此函式來標示所有的線段長度！嚴禁自行使用 ax.plot 或 ax.annotate 畫弧線，否則座標會亂飛導致畫布爆炸！
範例寫法：`draw_dimension(ax, B, C, '5', mode='{dim_style}')`
"""

# ---------------- 共用畫圖存檔函式 (內建精準數學外掛) ----------------
def execute_and_save_plot(python_code, file_format, transparent):
    try:
        plt.close('all') 
        safe_code = re.sub(r'plt\.show\(\)', '', python_code)
        mpl.rcParams['svg.fonttype'] = 'none'
        
        # 【核心技術】植入給 AI 用的精準數學外掛函式
        def draw_dimension(ax, p1, p2, text, mode='full_arc', invert=False):
            import numpy as np
            p1 = np.array(p1, dtype=float)
            p2 = np.array(p2, dtype=float)
            v = p2 - p1
            L = np.linalg.norm(v)
            if L == 0: return
            mid = (p1 + p2) / 2
            
            # 控制彎曲程度與方向
            rad = 0.2 if not invert else -0.2
            perp = np.array([-v[1], v[0]]) / L
            if invert: perp = -perp
            
            # 動態調整數字的距離 (短線段離近一點，長線段離遠一點)
            offset = max(L * 0.12, 0.4)
            
            if mode == 'short_arc':
                # 精準算出 15% 處的座標
                p1_inner = p1 + v * 0.15
                p2_inner = p2 - v * 0.15
                # 畫出兩端完美的小短弧
                ax.annotate('', xy=p1, xytext=p1_inner, arrowprops=dict(arrowstyle='-', connectionstyle=f'arc3,rad={-rad}', color='black'))
                ax.annotate('', xy=p2, xytext=p2_inner, arrowprops=dict(arrowstyle='-', connectionstyle=f'arc3,rad={rad}', color='black'))
                
                t_pos = mid + perp * (offset * 0.6)
                ax.text(t_pos[0], t_pos[1], text, fontsize=18, ha='center', va='center', bbox=dict(fc='white', ec='none', pad=0.1))
                
            elif mode == 'full_arc':
                ax.annotate('', xy=p1, xytext=p2, arrowprops=dict(arrowstyle='-', connectionstyle=f'arc3,rad={rad}', color='black'))
                t_pos = mid + perp * offset
                ax.text(t_pos[0], t_pos[1], text, fontsize=18, ha='center', va='center', bbox=dict(fc='white', ec='none', pad=0.1))
            else:
                # 無標線
                t_pos = mid + perp * (offset * 0.5)
                ax.text(t_pos[0], t_pos[1], text, fontsize=18, ha='center', va='center', bbox=dict(fc='white', ec='none', pad=0.1))

        # 建立專屬執行環境，將外掛函式放進去
        exec_globals = globals().copy()
        exec_globals['draw_dimension'] = draw_dimension
        
        exec(safe_code, exec_globals)
        fig = plt.gcf()
        
        if not fig.axes:
            raise ValueError("程式碼沒有產生任何有效的 matplotlib 圖形。")
            
        if transparent:
            fig.patch.set_alpha(0.0)
            for ax in fig.axes:
                ax.patch.set_alpha(0.0)
                
        file_path = f"output.{file_format}"
        # 恢復 0.0 白邊，因為弧線不會再亂飛了
        fig.savefig(file_path, format=file_format, bbox_inches='tight', pad_inches=0.0, transparent=transparent, dpi=300)
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
                        4. 畫布大小 `plt.figure(figsize=(6, 6))`。使用 `ax.set_xlim()` 和 `ax.set_ylim()` 留白約 0.5 到 0.8 個單位防裁切即可，不要讓圖形比例變小。
                        {latex_instruction}
                        6. 附圖只能畫出給定的「已知條件」，絕對不可以畫出要求解的「答案」或輔助線！
                        7. 隱藏座標軸：`plt.axis('off')`。
                        {dim_instruction}
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
4. 畫布大小 `plt.figure(figsize=(6, 6))`。使用 `ax.set_xlim()` 和 `ax.set_ylim()` 在上下左右各保留約 0.5 個單位即可。
{latex_instruction}
6. 只標示給定的已知條件，絕對不可以畫出答案！
7. 隱藏座標軸：`plt.axis('off')`。
{dim_instruction}"""
        
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