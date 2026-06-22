import streamlit as st
import random
import re
import os

# 动态获取当前代码所在的文件夹 (兼容电脑本地与云端)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ==================== 核心解析引擎 ====================
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
        # 移除了对“小听写”的特殊识别，全量走数字解析
        if '-' in part:
            bounds = part.split('-')
            if len(bounds) == 2 and bounds[0].strip().isdigit() and bounds[1].strip().isdigit():
                start, end = int(bounds[0].strip()), int(bounds[1].strip())
                if start > end: start, end = end, start
                for i in range(start, end + 1): filenames.append(f"list {i}.txt")
        elif part.isdigit():
            filenames.append(f"list {part}.txt")
    return list(dict.fromkeys(filenames))


# ==================== 状态管理初始化 ====================
if 'stage' not in st.session_state: st.session_state.stage = 'setup'
if 'sys_mode' not in st.session_state: st.session_state.sys_mode = 'learning'  # 'learning' or 'testing'
if 'total_count' not in st.session_state: st.session_state.total_count = 0

# 学习模式 (微循环+滚雪球) 专属状态
if 'unseen' not in st.session_state: st.session_state.unseen = []
if 'active' not in st.session_state: st.session_state.active = []
if 'snowball' not in st.session_state: st.session_state.snowball = []
if 'snowball_queue' not in st.session_state: st.session_state.snowball_queue = []
if 'need_snowball' not in st.session_state: st.session_state.need_snowball = False
if 'mastered_count' not in st.session_state: st.session_state.mastered_count = 0

# 词测模式 (盲测) 专属状态
if 'test_pool' not in st.session_state: st.session_state.test_pool = []
if 'test_wrong' not in st.session_state: st.session_state.test_wrong = []

# 共用状态
if 'current_word' not in st.session_state: st.session_state.current_word = None
if 'card_flipped' not in st.session_state: st.session_state.card_flipped = False
if 'round_num' not in st.session_state: st.session_state.round_num = 1


# ==================== 核心控制逻辑 ====================
def prepare_words(new_str, old_str, pct):
    new_files = parse_input_to_filenames(new_str)
    new_words = []
    for f in new_files: new_words.extend(parse_txt(os.path.join(BASE_DIR, f)))

    old_files = parse_input_to_filenames(old_str)
    old_words = []
    for f in old_files:
        if f not in new_files: old_words.extend(parse_txt(os.path.join(BASE_DIR, f)))

    if not new_words and not old_words: return []

    if old_words and new_words:
        desired_old = min(int(len(new_words) * 0.3 / 0.7), len(old_words))
        sampled_old = random.sample(old_words, desired_old)
    else:
        sampled_old = old_words if not new_words else []

    combined = new_words + sampled_old
    final_count = max(1, int(len(combined) * pct))
    return random.sample(combined, final_count)


def fetch_next_learning_card():
    st.session_state.card_flipped = False
    st.session_state.current_word = None

    # 1. 如果有雪球队列，优先处理雪球
    if st.session_state.snowball_queue:
        cw = st.session_state.snowball_queue.pop(0)
        cw['type'] = 'snowball'
        st.session_state.current_word = cw
        return

    # 2. 如果微循环为空
    if not st.session_state.active:
        # 是否需要触发组间雪球复习？
        if st.session_state.need_snowball and st.session_state.snowball:
            st.session_state.snowball_queue = st.session_state.snowball.copy()
            random.shuffle(st.session_state.snowball_queue)
            st.session_state.need_snowball = False
            cw = st.session_state.snowball_queue.pop(0)
            cw['type'] = 'snowball'
            st.session_state.current_word = cw
            return

        # 抽取新的10个词进入微循环
        if st.session_state.unseen:
            while len(st.session_state.active) < 10 and st.session_state.unseen:
                w, m = st.session_state.unseen.pop(0)
                st.session_state.active.append({'w': w, 'm': m, 'lvl': 0})
            st.session_state.need_snowball = True  # 等这组干完，触发雪球
        else:
            # 词库全空，结束！
            st.session_state.stage = 'success'
            return

    # 3. 处理微循环的词
    random.shuffle(st.session_state.active)
    cw = st.session_state.active.pop(0)
    cw['type'] = 'micro'
    st.session_state.current_word = cw


def handle_micro_rating(rating):
    cw = st.session_state.current_word
    if rating == 'red':
        cw['lvl'] = 0
        st.session_state.active.append(cw)
    elif rating == 'yellow':
        st.session_state.active.append(cw)
    elif rating == 'green':
        cw['lvl'] += 1
        if cw['lvl'] >= 3:
            st.session_state.snowball.append({'w': cw['w'], 'm': cw['m']})
        else:
            st.session_state.active.append(cw)
    fetch_next_learning_card()


def handle_snowball_rating(rating):
    cw = st.session_state.current_word
    if rating == 'green':
        # 彻底斩杀！从雪球库移除
        st.session_state.snowball = [item for item in st.session_state.snowball if item['w'] != cw['w']]
        st.session_state.mastered_count += 1
    elif rating == 'red':
        # 忘记了，降级打回微循环重新死磕
        st.session_state.snowball = [item for item in st.session_state.snowball if item['w'] != cw['w']]
        st.session_state.active.append({'w': cw['w'], 'm': cw['m'], 'lvl': 0})
    fetch_next_learning_card()


def flip_card(): st.session_state.card_flipped = True


def handle_test_rating(is_correct):
    cw = st.session_state.current_word
    if not is_correct: st.session_state.test_wrong.append(cw)

    st.session_state.card_flipped = False
    if st.session_state.test_pool:
        st.session_state.current_word = st.session_state.test_pool.pop(0)
    else:
        st.session_state.stage = 'review' if st.session_state.test_wrong else 'success'


# ==================== UI 渲染 ====================
st.set_page_config(page_title="智能单词训练", page_icon="🪶", layout="centered")

if st.session_state.stage == 'setup':
    st.title("🪶 智能单词训练系统")
    st.markdown("---")

    mode = st.radio("选择训练模式：",
                    options=['learning', 'testing'],
                    format_func=lambda
                        x: "🧠 背单词模式 (微循环 + 滚雪球闪卡)" if x == 'learning' else "🎯 词测模式 (严格盲测)")

    new_unit = st.text_input("🎯 新单元 (直接输入数字，如：5 或 5-7):", value="1")
    old_unit = st.text_input("📚 旧单元 (多单元用逗号，连续用短横杠，如：1-3, 5):")

    st.write("请选择本次听写的总量范围：")
    col1, col2, col3, col4 = st.columns(4)


    def start_app(pct):
        words = prepare_words(new_unit, old_unit, pct)
        if not words:
            st.error("没有读取到有效的单词，请检查数字是否正确！")
            return

        st.session_state.sys_mode = mode
        st.session_state.total_count = len(words)
        st.session_state.card_flipped = False

        if mode == 'learning':
            st.session_state.unseen = words
            st.session_state.active = []
            st.session_state.snowball = []
            st.session_state.snowball_queue = []
            st.session_state.need_snowball = False
            st.session_state.mastered_count = 0
            fetch_next_learning_card()
            st.session_state.stage = 'learning_ui'
        else:
            st.session_state.test_pool = [{'w': w, 'm': m} for w, m in words]
            st.session_state.test_wrong = []
            st.session_state.round_num = 1
            st.session_state.current_word = st.session_state.test_pool.pop(0)
            st.session_state.stage = 'testing_ui'


    if col1.button("25%"): start_app(0.25)
    if col2.button("50%"): start_app(0.50)
    if col3.button("75%"): start_app(0.75)
    if col4.button("100%"): start_app(1.0)

elif st.session_state.stage == 'learning_ui':
    cw = st.session_state.current_word
    # 计算顶部进度
    progress = st.session_state.mastered_count / st.session_state.total_count if st.session_state.total_count else 0

    # 顶部状态栏
    st.progress(progress)
    col1, col2 = st.columns(2)
    with col1:
        if cw['type'] == 'micro':
            st.caption(f"🔄 当前死磕微循环 (阶段熟练度: {cw['lvl']}/3)")
        else:
            st.caption(f"❄️ 跨组滚雪球复习 (斩杀或打回)")
    with col2:
        st.caption(
            f"<div style='text-align: right;'>彻底斩杀: {st.session_state.mastered_count}/{st.session_state.total_count}</div>",
            unsafe_allow_html=True)

    st.write("")
    st.write("")
    st.markdown(f"<h1 style='text-align: center; font-size: 4rem;'>{cw['w']}</h1>", unsafe_allow_html=True)
    st.write("")
    st.write("")

    if not st.session_state.card_flipped:
        st.button("👀 点击看释义", on_click=flip_card, use_container_width=True, type="primary")
    else:
        st.markdown(
            f"<div style='text-align: center; font-size: 1.2rem; color: #555; padding: 20px; background-color: #f0f2f6; border-radius: 10px; margin-bottom: 30px;'>{cw['m']}</div>",
            unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        if cw['type'] == 'micro':
            c1.button("🔴 忘记 (重新插队)", on_click=handle_micro_rating, args=('red',), use_container_width=True)
            c2.button("🟡 模糊 (稍后重试)", on_click=handle_micro_rating, args=('yellow',), use_container_width=True)
            c3.button("🟢 秒出 (熟练+1)", on_click=handle_micro_rating, args=('green',), use_container_width=True)
        else:
            c1.button("🔴 忘了 (打回死磕)", on_click=handle_snowball_rating, args=('red',), use_container_width=True)
            c2.empty()  # 雪球模式不需要中间状态
            c3.button("🟢 秒出 (彻底斩杀)", on_click=handle_snowball_rating, args=('green',), use_container_width=True)

elif st.session_state.stage == 'testing_ui':
    cw = st.session_state.current_word
    remain = len(st.session_state.test_pool) + 1

    st.caption(f"🎯 第 {st.session_state.round_num} 轮盲测 • 本轮剩余: {remain}")
    st.markdown(f"<h1 style='text-align: center; font-size: 4rem;'>{cw['w']}</h1>", unsafe_allow_html=True)
    st.write("")
    st.write("")

    if not st.session_state.card_flipped:
        st.button("🤔 脑海中想出答案后点击", on_click=flip_card, use_container_width=True, type="primary")
    else:
        st.markdown(
            f"<div style='text-align: center; font-size: 1.2rem; color: #555; padding: 20px; background-color: #f0f2f6; border-radius: 10px; margin-bottom: 30px;'>{cw['m']}</div>",
            unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c1.button("❌ 没想全 / 想错了", on_click=handle_test_rating, args=(False,), use_container_width=True)
        c2.button("✅ 完全想对了", on_click=handle_test_rating, args=(True,), use_container_width=True)

elif st.session_state.stage == 'review':
    st.error(f"🚨 本轮错题 / 待学库 (共 {len(st.session_state.test_wrong)} 词)")
    for cw in st.session_state.test_wrong:
        st.markdown(f"**{cw['w']}** &nbsp;&nbsp; <span style='color: gray;'>{cw['m']}</span>", unsafe_allow_html=True)
        st.markdown("---")


    def next_test_round():
        st.session_state.test_pool = st.session_state.test_wrong.copy()
        random.shuffle(st.session_state.test_pool)
        st.session_state.test_wrong = []
        st.session_state.round_num += 1
        st.session_state.current_word = st.session_state.test_pool.pop(0)
        st.session_state.card_flipped = False
        st.session_state.stage = 'testing_ui'


    st.button("开始下一轮盲测", type="primary", on_click=next_test_round, use_container_width=True)

elif st.session_state.stage == 'success':
    st.balloons()
    st.success("🎉 太棒了！本组单词已全部斩杀完毕！休息一下吧！")


    def reset_app():
        for key in list(st.session_state.keys()):
            del st.session_state[key]


    st.button("返回主界面 (测下一单元)", on_click=reset_app, use_container_width=True)