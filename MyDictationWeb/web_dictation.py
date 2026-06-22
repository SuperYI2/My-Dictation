import streamlit as st
import random
import re
import os

# 【核心修改】动态获取当前代码所在的文件夹，这样不管在电脑还是在云端都能找到文件
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ... 下面的代码完全不用动 ...


# ==================== 核心算法区 (与之前完全一致) ====================
def extract_and_clean(text):
    if not text: return set(), set()
    text = text.lower()
    text = re.sub(r'\b(adj|adv|n|v\.?t\.?|v\.?i\.?|v|prep|conj|pron|num|art|int)([\.。\s]|(?=[\u4e00-\u9fa5]))', '',
                  text)
    paren_matches = re.findall(r'[\(（].*?[\)）]', text)
    paren_set = set()
    for p in paren_matches:
        cleaned_p = re.sub(r'[^a-z0-9\u4e00-\u9fa5\(\)（）]', '', p)
        cleaned_p = cleaned_p.replace('（', '(').replace('）', ')')
        if cleaned_p != '()': paren_set.add(cleaned_p)
    core_text = re.sub(r'[\(（].*?[\)）]', ' ', text)
    chunks = re.split(r'[;；,，、\s]+', core_text)
    core_set = set()
    for c in chunks:
        c = re.sub(r'[^a-z0-9\u4e00-\u9fa5]', '', c)
        if c: core_set.add(c)
    return core_set, paren_set


def parse_txt(filepath):
    if not os.path.exists(filepath):
        st.error(f"找不到文件: {os.path.basename(filepath)}")
        return []
    content = ""
    for enc in ['utf-8-sig', 'gb18030', 'utf-16', 'utf-8']:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                content = f.read()
            break
        except Exception:
            continue
    words_pool = []
    current_word, current_meaning = "", []
    lines = content.replace('\r', '\n').split('\n')
    for line in lines:
        line = line.strip()
        if not line: continue
        if re.match(r'^\d+[\.\s]+', line):
            if current_word: words_pool.append((current_word, " ".join(current_meaning)))
            clean_line = re.sub(r'^\d+[\.\s]+', '', line)
            match = re.search(r'(\s+[a-z\.]+\.)|([\u4e00-\u9fa5])', clean_line)
            if match:
                idx = match.start()
                current_word = clean_line[:idx].strip()
                current_meaning = [clean_line[idx:].strip()]
            else:
                parts = clean_line.split(' ', 1)
                current_word = parts[0].strip()
                current_meaning = [parts[1].strip() if len(parts) > 1 else ""]
        else:
            if current_word: current_meaning.append(line)
    if current_word: words_pool.append((current_word, " ".join(current_meaning)))
    return words_pool


def parse_input_to_filenames(input_str):
    if not input_str.strip(): return []
    input_str = re.sub(r'[，、；;]', ',', input_str)
    input_str = re.sub(r'[—－~～]', '-', input_str)
    filenames = []
    parts = input_str.split(',')
    for part in parts:
        part = part.strip()
        if not part: continue
        if part == "小听写":
            filenames.append("小听写.txt")
        elif '-' in part:
            bounds = part.split('-')
            if len(bounds) == 2 and bounds[0].strip().isdigit() and bounds[1].strip().isdigit():
                start, end = int(bounds[0].strip()), int(bounds[1].strip())
                if start > end: start, end = end, start
                for i in range(start, end + 1): filenames.append(f"list {i}.txt")
        elif part.isdigit():
            filenames.append(f"list {part}.txt")
    return list(dict.fromkeys(filenames))


# ==================== 网页状态管理 ====================
# Streamlit 每次交互都会重头跑代码，所以需要用 session_state 记住数据
if 'stage' not in st.session_state:
    st.session_state.stage = 'setup'  # 阶段：setup, dictation, review, success
if 'current_pool' not in st.session_state:
    st.session_state.current_pool = []
if 'next_pool' not in st.session_state:
    st.session_state.next_pool = []
if 'current_idx' not in st.session_state:
    st.session_state.current_idx = 0
if 'round_num' not in st.session_state:
    st.session_state.round_num = 1

# ==================== 界面渲染逻辑 ====================
st.set_page_config(page_title="智能单词听写", page_icon="🪶")

if st.session_state.stage == 'setup':
    st.title("🪶 智能单词听写系统")
    st.markdown("---")

    new_unit = st.text_input("🎯 新单元 (支持数字/范围/“小听写”):", value="小听写")
    old_unit = st.text_input("📚 旧单元 (多单元用逗号，连续用短横杠):")

    st.info(f"📂 目标目录: `{BASE_DIR}`\n\n💡 混合模式下新旧词自动保持 7:3 黄金比例。")

    st.write("请选择本次听写的总量范围：")
    col1, col2, col3, col4 = st.columns(4)


    def start_dictation(pct):
        new_files = parse_input_to_filenames(new_unit)
        new_words = []
        for f in new_files: new_words.extend(parse_txt(os.path.join(BASE_DIR, f)))

        old_files = parse_input_to_filenames(old_unit)
        old_words = []
        for f in old_files:
            if f not in new_files: old_words.extend(parse_txt(os.path.join(BASE_DIR, f)))

        if not new_words and not old_words:
            st.error("没有读取到有效的单词，请检查配置！")
            return

        if old_words and new_words:
            desired_old_count = min(int(len(new_words) * 0.3 / 0.7), len(old_words))
            sampled_old = random.sample(old_words, desired_old_count)
        else:
            sampled_old = old_words if not new_words else []

        combined = new_words + sampled_old
        final_count = max(1, int(len(combined) * pct))

        st.session_state.current_pool = random.sample(combined, final_count)
        st.session_state.next_pool = []
        st.session_state.current_idx = 0
        st.session_state.round_num = 1
        st.session_state.stage = 'dictation'
        st.rerun()  # 刷新网页进入下一阶段


    if col1.button("25%"): start_dictation(0.25)
    if col2.button("50%"): start_dictation(0.50)
    if col3.button("75%"): start_dictation(0.75)
    if col4.button("100%"): start_dictation(1.0)

elif st.session_state.stage == 'dictation':
    pool_size = len(st.session_state.current_pool)
    curr_idx = st.session_state.current_idx
    word, correct_meaning = st.session_state.current_pool[curr_idx]

    st.caption(f"第 {st.session_state.round_num} 轮 • 进度: {curr_idx + 1} / {pool_size}")
    st.markdown(f"<h1 style='text-align: center; font-size: 3rem;'>{word}</h1>", unsafe_allow_html=True)
    st.write("")

    # 使用 form 来实现回车提交
    with st.form(key="dictation_form", clear_on_submit=True):
        user_input = st.text_input("输入释义 (乱序/无标点/括号内可省略，写则须精确)：")
        submitted = st.form_submit_button("确定 (Enter)", use_container_width=True)

        if submitted:
            user_cores, user_parens = extract_and_clean(user_input)
            correct_cores, correct_parens = extract_and_clean(correct_meaning)

            is_correct = False
            if user_cores == correct_cores and user_parens.issubset(correct_parens):
                is_correct = True

            if not is_correct:
                st.session_state.next_pool.append((word, correct_meaning, user_input))

            st.session_state.current_idx += 1
            if st.session_state.current_idx >= len(st.session_state.current_pool):
                st.session_state.stage = 'success' if not st.session_state.next_pool else 'review'
            st.rerun()

elif st.session_state.stage == 'review':
    st.error("🚨 本轮错题 / 待学库")

    for w, m, u in st.session_state.next_pool:
        display_u = u if u else "❌ (未填写)"
        st.markdown(f"**{w}**")
        st.markdown(f"<span style='color: gray;'>标准: {m}</span>", unsafe_allow_html=True)
        st.markdown(f"<span style='color: #E64340;'>你的: {display_u}</span>", unsafe_allow_html=True)
        st.markdown("---")

    if st.button("开始下一轮复习", type="primary", use_container_width=True):
        st.session_state.current_pool = [(w, m) for w, m, _ in st.session_state.next_pool]
        random.shuffle(st.session_state.current_pool)
        st.session_state.next_pool = []
        st.session_state.current_idx = 0
        st.session_state.round_num += 1
        st.session_state.stage = 'dictation'
        st.rerun()

elif st.session_state.stage == 'success':
    st.balloons()  # 放飞气球特效！
    st.success("🎉 太棒了！本组单词已全部斩杀完毕！")
    if st.button("返回主界面 (继续下一单元)", use_container_width=True):
        st.session_state.stage = 'setup'
        st.rerun()