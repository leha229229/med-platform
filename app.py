import streamlit as st
import psycopg2
import psycopg2.extras
import requests
import json
import time
import re

# ==========================================
# НАСТРОЙКИ
# ==========================================
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]
except Exception as e:
    st.error("⚠️ Ошибка: Не настроены секреты GROQ_API_KEY или ADMIN_PASSWORD.")
    st.stop()

DB_URI = "postgresql://postgres.dnmxpwggsbyrgqsegmcm:zqE-J4a-3hh-FwL@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

# ==========================================
# РАБОТА С БАЗОЙ
# ==========================================
def get_db_connection():
    return psycopg2.connect(DB_URI)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    conn.commit()
    conn.close()

init_db()

def parse_case_row(r):
    d = dict(r)
    desc = d.get('description', '') or ''
    
    q_from_col = d.get('questions')
    if q_from_col:
        if isinstance(q_from_col, str):
            try: d['questions'] = json.loads(q_from_col)
            except: d['questions'] = None
        else:
            d['questions'] = q_from_col
            
    if not d.get('questions') and "[ВОПРОСЫ:" in desc:
        q_str = desc.split("[ВОПРОСЫ:")[1].split("]")[0].strip()
        try: d['questions'] = json.loads(q_str)
        except: pass

    d['job_title'] = d.get('job_title') or 'Специалист'
    if "[ДОЛЖНОСТЬ:" in desc:
        d['job_title'] = desc.split("[ДОЛЖНОСТЬ:")[1].split("]")[0].strip()
        d['description'] = desc.split("[ДОЛЖНОСТЬ:")[0].strip()
        
    return d

def get_approved_cases(category=None, max_salary=None):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    query = "SELECT * FROM cases WHERE status = 'approved'"
    params = []
    
    if category:
        query += " AND category = %s"
        params.append(category)
        
    if max_salary:
        query += " AND min_salary <= %s"
        params.append(max_salary)
        
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return [parse_case_row(r) for r in rows]

def get_pending_cases():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM cases WHERE status = 'pending'")
    rows = cursor.fetchall()
    conn.close()
    return [parse_case_row(r) for r in rows]

def add_case(title, description, difficulty, company, category, min_salary, job_title, questions_json):
    conn = get_db_connection()
    cursor = conn.cursor()
    safe_desc = f"{description}\n\n[ДОЛЖНОСТЬ: {job_title}]"
    
    cursor.execute(
        "INSERT INTO cases (title, description, difficulty, company, status, category, min_salary, questions) VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s)",
        (title, safe_desc, difficulty, company, category, min_salary, questions_json)
    )
    conn.commit()
    conn.close()

def update_case_status(case_id, new_status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE cases SET status = %s WHERE id = %s", (new_status, case_id))
    conn.commit()
    conn.close()

def delete_case(case_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cases WHERE id = %s", (case_id,))
    conn.commit()
    conn.close()

# ==========================================
# JS-ЗАЩИТА ОТ ВСТАВКИ
# ==========================================
js_block_paste = """
<script>
    setTimeout(function() {
        const textareas = window.parent.document.querySelectorAll('textarea');
        textareas.forEach(ta => {
            ta.addEventListener('paste', function(e) {
                e.preventDefault();
                alert('Вставка текста запрещена! Пожалуйста, введите ответ вручную.');
            });
            ta.addEventListener('contextmenu', function(e) { e.preventDefault(); });
        });
    }, 1000);
</script>
"""
st.markdown(js_block_paste, unsafe_allow_html=True)

# ==========================================
# АВТОРИЗАЦИЯ
# ==========================================
st.sidebar.title("Управление")
admin_pass_input = st.sidebar.text_input("Пароль администратора", type="password")
is_admin = False
if admin_pass_input == ADMIN_PASSWORD:
    is_admin = True
    st.sidebar.success("✅ Вы вошли как Администратор")

if 'user_role' not in st.session_state:
    st.session_state['user_role'] = None

if not is_admin and st.session_state['user_role'] is None:
    st.title("🩺 Добро пожаловать!")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🎓 Я Студент", use_container_width=True):
            st.session_state['user_role'] = 'student'
            st.rerun()
    with col2:
        if st.button("🏢 Я Компания", use_container_width=True):
            st.session_state['user_role'] = 'company'
            st.rerun()
    st.stop()

role = 'admin' if is_admin else st.session_state['user_role']
st.set_page_config(page_title="МедПлатформа", page_icon="🩺")
st.title("🩺 МедПлатформа")

# ==========================================
# ЛОГИКА ДЛЯ СТУДЕНТОВ
# ==========================================
if role == 'student':
    if not st.session_state.get('interview_active', False):
        st.subheader("Выберите сферу и желаемую зарплату:")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🧪 НИИ", use_container_width=True):
                st.session_state['current_category'] = 'НИИ'
        with col2:
            if st.button("🏥 Больницы", use_container_width=True):
                st.session_state['current_category'] = 'Больницы'
        with col3:
            if st.button("💊 Фарм-маркетинг", use_container_width=True):
                st.session_state['current_category'] = 'Фарм-маркетинг'
        
        # Возвращаем ползунок зарплаты
        target_salary = st.slider("Ваша целевая зарплата (₽)", min_value=40000, max_value=150000, value=80000, step=5000)
                
        if 'current_category' in st.session_state:
            st.divider()
            st.subheader(f"Доступные собеседования: {st.session_state['current_category']}")
            # Фильтруем кейсы по зарплате!
            cases = get_approved_cases(st.session_state['current_category'], target_salary)
            
            if not cases:
                st.info(f"В сфере «{st.session_state['current_category']}» пока нет кейсов с зарплатой до {target_salary} ₽. Попробуйте выбрать другую сферу или повысить планку.")
            
            for c in cases:
                with st.container():
                    st.markdown(f"### {c.get('title', 'Без названия')}")
                    st.caption(f"🏢 {c.get('company', 'Неизвестно')} | 💼 {c.get('job_title', 'Специалист')} | 💰 от {c.get('min_salary', 40000)} ₽ | 📊 {c.get('difficulty', 'Средний')}")
                    st.write(c.get('description', 'Нет описания'))
                    
                    if st.button(f"Пройти собеседование", key=f"start_{c['id']}"):
                        st.session_state['interview_active'] = True
                        st.session_state['current_case'] = c
                        st.session_state['current_q_idx'] = 0
                        st.session_state['interview_answers'] = []
                        st.rerun()
                    st.divider()
                    
    else:
        c = st.session_state['current_case']
        questions = c.get('questions')
        
        if not questions:
            st.error("⚠️ В этом кейсе пока нет вопросов. Пожалуйста, выберите другой кейс.")
            if st.button("Назад в меню"):
                st.session_state['interview_active'] = False
                st.rerun()
            st.stop()
            
        if isinstance(questions, str):
            try:
                questions = json.loads(questions)
            except:
                st.error("⚠️ Ошибка в формате вопросов.")
                st.stop()
            
        idx = st.session_state['current_q_idx']
        
        if idx < len(questions):
            q = questions[idx]
            st.subheader(f"{c.get('title', 'Собеседование')} (Вопрос {idx+1} из {len(questions)})")
            
            with st.expander("📄 Показать описание кейса", expanded=True):
                st.write(c.get('description', 'Нет описания'))
                
            st.markdown(f"**Вопрос:** {q['question']}")
            
            ans = st.text_area("Ваш ответ:", key=f"q_{idx}")
            if st.button("Ответить"):
                if ans:
                    with st.spinner("Проверяем ответ..."):
                        prompt = f"Вопрос: {q['question']}\nЭталон: {q['correct_answer']}\nОтвет студента: {ans}\n\nОцени кратко (1-2 предложения), верно ли студент ответил, и что упустил. Без лишних вступлений и без звездочек."
                        url = "https://api.groq.com/openai/v1/chat/completions"
                        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                        payload = {"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": prompt}], "max_tokens": 150, "temperature": 0.1}
                        
                        try:
                            res = requests.post(url, headers=headers, json=payload, timeout=15)
                            mini_feedback = res.json()['choices'][0]['message']['content'].replace("**", "")
                            st.session_state['interview_answers'].append({"q": q['question'], "ans": ans, "feedback": mini_feedback})
                            st.session_state['current_q_idx'] += 1
                            st.rerun()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")
                else:
                    st.warning("Напишите ответ!")
        else:
            st.success("Собеседование завершено!")
            st.subheader("Ваши ответы:")
            for item in st.session_state['interview_answers']:
                st.markdown(f"**Вопрос:** {item['q']}")
                st.info(f"**Ответ:** {item['ans']}")
                st.caption(f"🤖 {item['feedback']}")
                
            st.divider()
            if st.button("Получить итоговый вердикт и рекомендации"):
                with st.spinner("Формируем итог..."):
                    qa_text = ""
                    for item in st.session_state['interview_answers']:
                        qa_text += f"Вопрос: {item['q']}\nОтвет: {item['ans']}\nФидбек: {item['feedback']}\n\n"
                        
                    # Запрещаем звездочки в промпте
                    prompt = f"""
                    Ты — HR-директор. Студент проходил собеседование на должность "{c.get('job_title', 'Специалист')}" с зарплатой от {c.get('min_salary', 40000)} ₽.
                    Вот его ответы:
                    {qa_text}
                    
                    Сделай вывод:
                    1. Вердикт (Одобрено на X / Рекомендуем Y).
                    2. Общий фидбек: сильные и слабые стороны, план развития.
                    
                    ВАЖНО: Пиши обычным текстом. НЕ ИСПОЛЬЗУЙ символы Markdown (звездочки **, решетки #).
                    
                    ФОРМАТ:
                    Вердикт: [Текст]
                    Фидбек: [Текст]
                    """
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                    payload = {"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": prompt}], "max_tokens": 400, "temperature": 0.1}
                    
                    try:
                        res = requests.post(url, headers=headers, json=payload, timeout=15)
                        result_text = res.json()['choices'][0]['message']['content']
                        
                        # Очищаем от звездочек перед парсингом
                        clean_text = result_text.replace("**", "").replace("#", "")
                        
                        verdict = re.search(r'Вердикт:\s*(.*?)(?=\n|Фидбек|$)', clean_text, re.IGNORECASE | re.DOTALL)
                        feedback = re.search(r'Фидбек:\s*(.*)', clean_text, re.IGNORECASE | re.DOTALL)
                        
                        v_text = verdict.group(1).strip() if verdict else 'Одобрено (по результатам)'
                        f_text = feedback.group(1).strip() if feedback else clean_text
                        
                        st.success(f"**Вердикт:** {v_text}")
                        st.info(f"**Фидбек:** {f_text}")
                        
                        if st.button("На главную"):
                            st.session_state['interview_active'] = False
                            st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка: {e}")

# ==========================================
# ЛОГИКА ДЛЯ КОМПАНИЙ И АДМИНА
# ==========================================
elif role == 'company' or is_admin:
    if is_admin:
        tabs = st.tabs(["📚 Все кейсы", "➕ Добавить кейс", "🛡️ Модерация"])
        tab1, tab2, tab3 = tabs
    else:
        tabs = st.tabs(["📚 База кейсов", "➕ Предложить кейс"])
        tab1, tab2 = tabs
        tab3 = None

    with tab1:
        st.subheader("Все одобренные кейсы" if is_admin else "База кейсов")
        cases = get_approved_cases()
        
        if not cases:
            st.info("Пока нет опубликованных кейсов.")
            
        for r in cases:
            with st.container():
                st.markdown(f"### {r.get('title', 'Без названия')}")
                st.caption(f"🏢 {r.get('company', 'Неизвестно')} | 💼 {r.get('job_title', 'Специалист')} | 💰 от {r.get('min_salary', 40000)} ₽ | 📊 {r.get('difficulty', 'Средний')}")
                st.write(r.get('description', 'Нет описания'))
                
                if is_admin:
                    if st.button(f"❌ Удалить #{r['id']}", key=f"del_admin_{r['id']}"):
                        delete_case(r['id'])
                        st.rerun()
                st.divider()

    with tab2:
        st.subheader("Добавить новый кейс")
        with st.form("add_case_form"):
            new_title = st.text_input("Название собеседования")
            new_company = st.text_input("Компания")
            new_job_title = st.text_input("Должность")
            new_category = st.selectbox("Направление", ["НИИ", "Больницы", "Фарм-маркетинг"])
            new_difficulty = st.selectbox("Сложность", ["Легкий", "Средний", "Сложный"])
            new_salary = st.number_input("Зарплата (от)", min_value=40000, max_value=150000, value=80000, step=5000)
            new_description = st.text_area("Краткое описание (для карточки)")
            
            st.write("Вопросы (Минимум 1):")
            q1 = st.text_area("Вопрос 1")
            a1 = st.text_area("Эталонный ответ 1")
            q2 = st.text_area("Вопрос 2 (необязательно)")
            a2 = st.text_area("Эталонный ответ 2 (необязательно)")
            
            if st.form_submit_button("Отправить"):
                questions = []
                if q1 and a1: questions.append({"question": q1, "correct_answer": a1})
                if q2 and a2: questions.append({"question": q2, "correct_answer": a2})
                
                if new_title and new_company and questions:
                    add_case(new_title, new_description, new_difficulty, new_company, new_category, new_salary, new_job_title, json.dumps(questions, ensure_ascii=False))
                    st.success("Кейс добавлен!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Заполните название, компанию и хотя бы 1 вопрос.")

    if tab3:
        with tab3:
            st.subheader("Кейсы на модерации")
            pending = get_pending_cases()
            if not pending:
                st.info("Нет новых кейсов.")
            for p in pending:
                st.markdown(f"### {p.get('title', 'Без названия')} ({p.get('company', 'Неизвестно')})")
                st.caption(f"💰 от {p.get('min_salary', 40000)} ₽")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✅ Одобрить #{p['id']}", key=f"app_{p['id']}"):
                        update_case_status(p['id'], 'approved')
                        st.rerun()
                with col2:
                    if st.button(f"❌ Удалить #{p['id']}", key=f"del_pend_{p['id']}"):
                        delete_case(p['id'])
                        st.rerun()
                st.divider()
