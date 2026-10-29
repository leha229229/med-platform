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
    st.error("⚠️ Ошибка: Не настроены секреты.")
    st.stop()

DB_URI = "postgresql://postgres.dnmxpwggsbyrgqsegmcm:zqE-J4a-3hh-FwL@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

# ==========================================
# РАБОТА С БАЗОЙ
# ==========================================
def get_db_connection():
    return psycopg2.connect(DB_URI)

def get_approved_cases(category=None):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if category:
        cursor.execute("SELECT * FROM cases WHERE status = 'approved' AND category = %s", (category,))
    else:
        cursor.execute("SELECT * FROM cases WHERE status = 'approved'")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_pending_cases():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM cases WHERE status = 'pending'")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_case(title, description, difficulty, company, category, min_salary, job_title, questions_json):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cases (title, description, difficulty, company, status, category, min_salary, job_title, questions) VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s, %s)",
        (title, description, difficulty, company, category, min_salary, job_title, questions_json)
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
# АВТОРИЗАЦИЯ И РОЛИ
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
# ЛОГИКА ИНТЕРВЬЮ (ДЛЯ СТУДЕНТА)
# ==========================================
if role == 'student':
    # Если тест не активен, показываем меню сфер
    if not st.session_state.get('interview_active', False):
        st.subheader("Выберите сферу для собеседования:")
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
                
        if 'current_category' in st.session_state:
            st.divider()
            st.subheader(f"Доступные собеседования: {st.session_state['current_category']}")
            cases = get_approved_cases(st.session_state['current_category'])
            
            if not cases:
                st.info("В этой сфере пока нет кейсов.")
            
            for c in cases:
                with st.container():
                    st.markdown(f"### {c['title']}")
                    st.caption(f"🏢 {c['company']} | 💼 {c.get('job_title', 'Специалист')} | 💰 от {c['min_salary']} ₽ | 📊 {c['difficulty']}")
                    st.write(c['description'])
                    
                    if st.button(f"Пройти собеседование", key=f"start_{c['id']}"):
                        st.session_state['interview_active'] = True
                        st.session_state['current_case'] = c
                        st.session_state['current_q_idx'] = 0
                        st.session_state['interview_answers'] = []
                        st.rerun()
                    st.divider()
                    
    # Если тест активен, показываем вопросы
    else:
        c = st.session_state['current_case']
        questions = c.get('questions')
        
        # Защита от пустых вопросов
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
                st.error("⚠️ Ошибка в формате вопросов. Обратитесь к администратору.")
                st.stop()
            
        idx = st.session_state['current_q_idx']
        
        if idx < len(questions):
            q = questions[idx]
            st.subheader(f"{c['title']} (Вопрос {idx+1} из {len(questions)})")
            st.write(q['question'])
            
            ans = st.text_area("Ваш ответ:", key=f"q_{idx}")
            if st.button("Ответить"):
                if ans:
                    # Мини-фидбек через ИИ
                    with st.spinner("Проверяем ответ..."):
                        prompt = f"Вопрос: {q['question']}\nЭталон: {q['correct_answer']}\nОтвет студента: {ans}\n\nОцени кратко (1-2 предложения), верно ли студент ответил, и что упустил. Без лишних вступлений."
                        url = "https://api.groq.com/openai/v1/chat/completions"
                        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                        payload = {"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": prompt}], "max_tokens": 150, "temperature": 0.1}
                        
                        try:
                            res = requests.post(url, headers=headers, json=payload, timeout=15)
                            mini_feedback = res.json()['choices'][0]['message']['content']
                            st.session_state['interview_answers'].append({"q": q['question'], "ans": ans, "feedback": mini_feedback})
                            st.session_state['current_q_idx'] += 1
                            st.rerun()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")
                else:
                    st.warning("Напишите ответ!")
        else:
            # Все вопросы пройдены - итоговый вердикт
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
                        
                    prompt = f"""
                    Ты — HR-директор. Студент проходил собеседование на должность "{c.get('job_title', 'Специалист')}" с зарплатой от {c['min_salary']} ₽.
                    Вот его ответы:
                    {qa_text}
                    
                    Сделай вывод:
                    1. Вердикт (Одобрено на X / Рекомендуем Y).
                    2. Общий фидбек: сильные и слабые стороны, план развития.
                    
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
                        
                        verdict = re.search(r'Вердикт:\s*(.*?)(?=\n|Фидбек|$)', result_text, re.IGNORECASE | re.DOTALL)
                        feedback = re.search(r'Фидбек:\s*(.*)', result_text, re.IGNORECASE | re.DOTALL)
                        
                        st.success(f"**Вердикт:** {verdict.group(1).strip() if verdict else 'Одобрено'}")
                        st.info(f"**Фидбек:** {feedback.group(1).strip() if feedback else ''}")
                        
                        if st.button("На главную"):
                            st.session_state['interview_active'] = False
                            st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка: {e}")

# ==========================================
# ЛОГИКА ДЛЯ КОМПАНИЙ
# ==========================================
elif role == 'company' or is_admin:
    tabs = st.tabs(["➕ Предложить кейс", "🛡️ Модерация (Админ)"]) if is_admin else st.tabs(["➕ Предложить кейс"])
    
    with tabs[0]:
        st.subheader("Создать новый кейс (Собеседование)")
        
        with st.form("add_case_form"):
            new_title = st.text_input("Название собеседования (например, 'Собеседование в отдел маркетинга')")
            new_company = st.text_input("Компания")
            new_job_title = st.text_input("Должность (например, 'Менеджер по продукту')")
            new_category = st.selectbox("Направление", ["НИИ", "Больницы", "Фарм-маркетинг"])
            new_difficulty = st.selectbox("Сложность", ["Легкий", "Средний", "Сложный"])
            new_salary = st.number_input("Зарплата (от)", min_value=40000, max_value=150000, value=80000, step=5000)
            new_description = st.text_area("Краткое описание (для карточки)")
            
            st.write("Вопросы (Минимум 1):")
            q1 = st.text_area("Вопрос 1")
            a1 = st.text_area("Эталонный ответ 1")
            q2 = st.text_area("Вопрос 2 (необязательно)")
            a2 = st.text_area("Эталонный ответ 2 (необязательно)")
            q3 = st.text_area("Вопрос 3 (необязательно)")
            a3 = st.text_area("Эталонный ответ 3 (необязательно)")
            
            if st.form_submit_button("Отправить на модерацию"):
                questions = []
                if q1 and a1: questions.append({"question": q1, "correct_answer": a1})
                if q2 and a2: questions.append({"question": q2, "correct_answer": a2})
                if q3 and a3: questions.append({"question": q3, "correct_answer": a3})
                
                if new_title and new_company and questions:
                    add_case(new_title, new_description, new_difficulty, new_company, new_category, new_salary, new_job_title, json.dumps(questions, ensure_ascii=False))
                    st.success("Отправлено на модерацию!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Заполните название, компанию и хотя бы 1 вопрос.")
                    
    if is_admin and len(tabs) > 1:
        with tabs[1]:
            st.subheader("На модерации")
            pending = get_pending_cases()
            for p in pending:
                st.markdown(f"### {p['title']} ({p['company']})")
                if st.button(f"✅ Одобрить #{p['id']}"):
                    update_case_status(p['id'], 'approved')
                    st.rerun()
                if st.button(f"❌ Удалить #{p['id']}"):
                    delete_case(p['id'])
                    st.rerun()
