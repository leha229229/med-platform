import streamlit as st
import psycopg2
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
# РАБОТА С POSTGRESQL
# ==========================================
def get_db_connection():
    return psycopg2.connect(DB_URI)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cases (
            id SERIAL PRIMARY KEY,
            title TEXT,
            description TEXT,
            difficulty TEXT,
            company TEXT,
            status TEXT DEFAULT 'pending',
            correct_answer TEXT,
            category TEXT
        )
    ''')
    # Миграция, если база была создана ранее без колонки category
    try:
        cursor.execute("ALTER TABLE cases ADD COLUMN category TEXT")
    except psycopg2.errors.DuplicateColumn:
        conn.rollback() # Откатываем транзакцию, если колонка уже есть
    conn.commit()
    conn.close()

init_db()

def get_approved_cases(category_filter=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if category_filter:
        cursor.execute("SELECT id, title, description, difficulty, company, correct_answer, category FROM cases WHERE status = 'approved' AND category = %s", (category_filter,))
    else:
        cursor.execute("SELECT id, title, description, difficulty, company, correct_answer, category FROM cases WHERE status = 'approved'")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "description": r[2], "difficulty": r[3], "company": r[4], "correct_answer": r[5], "category": r[6]} for r in rows]

def get_pending_cases():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, difficulty, company, correct_answer, category FROM cases WHERE status = 'pending'")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "description": r[2], "difficulty": r[3], "company": r[4], "correct_answer": r[5], "category": r[6]} for r in rows]

def add_case(title, description, difficulty, company, correct_answer, category):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cases (title, description, difficulty, company, status, correct_answer, category) VALUES (%s, %s, %s, %s, 'pending', %s, %s)",
        (title, description, difficulty, company, correct_answer, category)
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
st.sidebar.caption("Введите пароль для доступа к админ-панели.")
admin_pass_input = st.sidebar.text_input("Пароль администратора", type="password")

is_admin = False
if admin_pass_input == ADMIN_PASSWORD:
    is_admin = True
    st.sidebar.success("✅ Вы вошли как Администратор")

# Выбор роли (если не админ)
if 'user_role' not in st.session_state:
    st.session_state['user_role'] = None

if not is_admin and st.session_state['user_role'] is None:
    st.title("🩺 Добро пожаловать на МедПлатформу!")
    st.write("Пожалуйста, выберите, кто вы:")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🎓 Я Студент", use_container_width=True):
            st.session_state['user_role'] = 'student'
            st.rerun()
    with col2:
        if st.button("🏢 Я Компания", use_container_width=True):
            st.session_state['user_role'] = 'company'
            st.rerun()
    st.stop() # Останавливаем дальнейшую загрузку, пока не выберут роль

# ==========================================
# ОСНОВНОЙ ИНТЕРФЕЙС
# ==========================================
st.set_page_config(page_title="МедПлатформа", page_icon="🩺")
st.title("🩺 Платформа для студентов-медиков")

if is_admin:
    st.info("Режим Администратора: доступны все функции.")
    role = 'admin'
elif st.session_state['user_role'] == 'student':
    st.info("Вы вошли как Студент. Выберите кейс и проверьте свои силы.")
    role = 'student'
else:
    st.info("Вы вошли как Компания. Здесь вы можете предложить кейс и посмотреть уровень студентов.")
    role = 'company'

# ==========================================
# ВКЛАДКИ В ЗАВИСИМОСТИ ОТ РОЛИ
# ==========================================
if role == 'student':
    # Если студент, создаем только одну вкладку, но забираем её из списка [0]
    tab1 = st.tabs(["📚 Решение кейсов"])[0]
    tab2 = None
    tab3 = None
elif role == 'company':
    tab1, tab2 = st.tabs(["📚 База кейсов", "➕ Предложить кейс"])
    tab3 = None
elif role == 'admin':
    tab1, tab2, tab3 = st.tabs(["📚 Список кейсов", "➕ Предложить кейс", "🛡️ Модерация"])
# --- ВКЛАДКА 1: СПИСОК КЕЙСОВ (ДЛЯ ВСЕХ) ---
with tab1:
    if role == 'student':
        st.subheader("Выбери направление:")
        category_filter = st.radio("Фильтр по типу:", ["Все", "НИИ", "Больницы", "Фарм-маркетинг"], horizontal=True)
        cat_db = None if category_filter == "Все" else category_filter
        cases = get_approved_cases(cat_db)
    else:
        st.subheader("Опубликованные кейсы")
        cases = get_approved_cases()

    if cases:
        for case in cases:
            with st.container():
                st.markdown(f"### {case['title']}")
                st.caption(f"🏷️ {case['category']} | Сложность: {case['difficulty']} | Компания: {case['company']}")
                st.write(f"*{case['description']}*")
                
                if role in ['student', 'admin']:
                    if st.button(f"Решить кейс #{case['id']}", key=f"btn_{case['id']}"):
                        st.session_state['current_case'] = case
                        st.session_state['start_time'] = time.time()
                
                if role == 'admin':
                    if st.button(f"❌ Удалить #{case['id']}", key=f"del_approved_{case['id']}"):
                        delete_case(case['id'])
                        st.rerun()
                st.divider()
    else:
        st.info("Пока нет доступных кейсов в этой категории.")

# --- ВКЛАДКА 2: ПРЕДЛОЖИТЬ КЕЙС (ДЛЯ КОМПАНИЙ И АДМИНА) ---
if tab2:
    with tab2:
        st.subheader("Предложить новый кейс")
        st.info("💡 Ваш кейс будет опубликован на платформе только после проверки администратором.")
        
        with st.form("add_case_form"):
            new_title = st.text_input("Название кейса")
            new_company = st.text_input("Название компании")
            new_category = st.selectbox("Направление", ["НИИ", "Больницы", "Фарм-маркетинг"])
            new_difficulty = st.selectbox("Сложность", ["Легкий", "Средний", "Сложный"])
            new_description = st.text_area("Описание задачи (симптомы/условия)")
            new_correct_answer = st.text_area("Эталонный ответ (правильный диагноз/решение)")
            
            submit_button = st.form_submit_button("Отправить на модерацию")
            
            if submit_button:
                if new_title and new_company and new_correct_answer:
                    add_case(new_title, new_description, new_difficulty, new_company, new_correct_answer, new_category)
                    st.success("✅ Кейс отправлен на модерацию!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Заполните все обязательные поля.")

# --- ВКЛАДКА 3: МОДЕРАЦИЯ (ТОЛЬКО ДЛЯ АДМИНА) ---
if tab3:
    with tab3:
        st.subheader("Кейсы на модерации")
        pending = get_pending_cases()
        if pending:
            for p_case in pending:
                with st.container():
                    st.markdown(f"### {p_case['title']}")
                    st.caption(f"🏷️ {p_case['category']} | Компания: {p_case['company']}")
                    st.write(p_case['description'])
                    st.info(f"Эталонный ответ: {p_case['correct_answer']}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(f"✅ Одобрить #{p_case['id']}", key=f"app_{p_case['id']}"):
                            update_case_status(p_case['id'], 'approved')
                            st.rerun()
                    with col2:
                        if st.button(f"❌ Удалить #{p_case['id']}", key=f"del_{p_case['id']}"):
                            delete_case(p_case['id'])
                            st.rerun()
                    st.divider()
        else:
            st.info("Нет новых кейсов на модерации. Отдыхай!")

# ==========================================
# РЕШЕНИЕ КЕЙСА И АНТИПЛАГИАТ (ДЛЯ СТУДЕНТОВ И АДМИНА)
# ==========================================
if 'current_case' in st.session_state:
    case = st.session_state['current_case']
    st.divider()
    st.subheader(f"Решение кейса: {case['title']}")
    st.caption(f"🏷️ Категория: {case['category']}")
    
    student_answer = st.text_area("Напиши свой ответ:", height=150, key="student_answer_area")
    
    if st.button("Отправить на проверку ИИ"):
        if student_answer:
            time_spent = time.time() - st.session_state.get('start_time', time.time())
            chars_per_minute = (len(student_answer) / time_spent) * 60 if time_spent > 0 else 9999
            
            with st.spinner("Нейросеть анализирует ответ..."):
                # ДИНАМИЧЕСКИЙ ПРОМПТ В ЗАВИСИМОСТИ ОТ КАТЕГОРИИ
                if case['category'] == 'НИИ':
                    persona = "Ты — строгий научный рецензент в НИИ. Оцени, соблюдены ли принципы доказательной медицины, есть ли логические ошибки в выводах."
                elif case['category'] == 'Фарм-маркетинг':
                    persona = "Ты — коммерческий директор фарм-компании. Оцени ответ с точки зрения ROI, маржинальности, реалистичности бизнес-плана и знания рынка."
                else: # Больницы
                    persona = "Ты — заведующий отделением больницы. Оцени, провел ли студент дифференциальную диагностику, назначил ли правильные анализы и не навредил ли пациенту."

                prompt = f"""
                {persona}
                
                Кейс: "{case['description']}"
                ЭТАЛОННЫЙ ОТВЕТ: "{case['correct_answer']}"
                Ответ студента: "{student_answer}"
                
                Твоя задача: Оценить ответ студента по 100-балльной шкале, строго следуя критериям:
                1. (60 баллов) Правильно ли определена суть (диагноз/решение)?
                2. (20 баллов) Есть ли обоснование?
                3. (20 баллов) Упомянуты ли правильные методы/инструменты?
                
                ВАЖНО: Выведи ответ СТРОГО по шаблону:
                Оценка: [число от 1 до 100]/100
                Фидбек: [твой текст (2-3 предложения)]
                AI_SUSPECT: [YES или NO]
                """
                
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                payload = {"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": prompt}], "max_tokens": 500, "temperature": 0.1}
                
                try:
                    # Делаем до 2-х попыток, если ИИ отвечает не по формату
                    max_retries = 2
                    for attempt in range(max_retries):
                        response = requests.post(url, headers=headers, json=payload, timeout=15)
                        response.raise_for_status()
                        response_text = response.json()['choices'][0]['message']['content']
                        
                        score_match = re.search(r'Оценка:\s*(\d+)', response_text, re.IGNORECASE)
                        score = score_match.group(1) if score_match else None

                        if score is not None:
                            break # Если нашли оценку — выходим из цикла, всё ок
                        
                        # Если оценки нет, значит формат сломался. Пробуем еще раз с другим промптом
                        if attempt < max_retries - 1:
                            # Добавляем в промпт просьбу исправиться
                            payload["messages"][0]["content"] += "\n\nВНИМАНИЕ: Твой предыдущий ответ был не по формату. Строго соблюдай шаблон: Оценка: [число]/100 \n Фидбек: [текст] \n AI_SUSPECT: [YES/NO]"

                    if score is None:
                        st.error("⚠️ Нейросеть трижды не смогла ответить по формату. Попробуйте переформулировать ответ.")
                        st.code(response_text)
                        st.stop()

                    feedback_match = re.search(r'Фидбек:\s*(.*?)(?=AI_SUSPECT|$)', response_text, re.IGNORECASE | re.DOTALL)
                    feedback = feedback_match.group(1).strip() if feedback_match else "Не удалось распознать."

                    ai_suspect = "YES" if "AI_SUSPECT: YES" in response_text.upper().replace(" ", "") else "NO"
                    
                    st.success(f"Оценка: {score}/100")
                    st.info(f"Фидбек от ИИ: {feedback}")
                    
                    if ai_suspect == "YES" and chars_per_minute > 500:
                        st.error(f"🚨 Вердикт: СИЛЬНОЕ ПОДОЗРЕНИЕ НА ИИ. (Скорость ввода: {int(chars_per_minute)} симв/мин).")
                    else:
                        st.success("✅ Вердикт антиплагиата: Чисто.")
                        
                except requests.exceptions.Timeout:
                    st.error("⚠️ Таймаут. Нейросеть слишком долго думает. Попробуйте еще раз.")
                except Exception as e:
                    st.error(f"Ошибка: {str(e)}")
