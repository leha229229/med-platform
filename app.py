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
            category TEXT,
            min_salary INTEGER DEFAULT 40000
        )
    ''')
    # Миграции для новых колонок
    try:
        cursor.execute("ALTER TABLE cases ADD COLUMN category TEXT")
        cursor.execute("ALTER TABLE cases ADD COLUMN min_salary INTEGER DEFAULT 40000")
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    conn.commit()
    conn.close()

init_db()

def get_cases_by_salary(target_salary, category_filter=None):
    """Выбирает 3 кейса: 2 подходящих по зп, 1 на вырост (сложнее)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    base_query = "SELECT id, title, description, difficulty, company, correct_answer, category, min_salary FROM cases WHERE status = 'approved'"
    params = []
    
    if category_filter:
        base_query += " AND category = %s"
        params.append(category_filter)
        
    # Получаем все подходящие кейсы
    cursor.execute(base_query, tuple(params))
    all_cases = cursor.fetchall()
    conn.close()
    
    if not all_cases:
        return []

    # Сортируем по зарплате
    easy_cases = [c for c in all_cases if c[7] <= target_salary - 20000]
    target_cases = [c for c in all_cases if target_salary - 20000 < c[7] <= target_salary]
    hard_cases = [c for c in all_cases if c[7] > target_salary]

    import random
    selected = []
    
    # Берем 1 базовый, 1 целевой, 1 сложный (если есть)
    if easy_cases: selected.append(random.choice(easy_cases))
    if target_cases: selected.append(random.choice(target_cases))
    if hard_cases: selected.append(random.choice(hard_cases))
    
    # Если набрали меньше 3, добиваем чем есть
    while len(selected) < 3 and all_cases:
        c = random.choice(all_cases)
        if c not in selected:
            selected.append(c)

    # Форматируем в словари
    return [{"id": r[0], "title": r[1], "description": r[2], "difficulty": r[3], "company": r[4], "correct_answer": r[5], "category": r[6], "min_salary": r[7]} for r in selected[:3]]

def get_pending_cases():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, difficulty, company, correct_answer, category, min_salary FROM cases WHERE status = 'pending'")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "description": r[2], "difficulty": r[3], "company": r[4], "correct_answer": r[5], "category": r[6], "min_salary": r[7]} for r in rows]

def add_case(title, description, difficulty, company, correct_answer, category, min_salary):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cases (title, description, difficulty, company, status, correct_answer, category, min_salary) VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s)",
        (title, description, difficulty, company, correct_answer, category, min_salary)
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

# ==========================================
# ИНТЕРФЕЙС
# ==========================================
st.set_page_config(page_title="МедПлатформа", page_icon="🩺")
st.title("🩺 Платформа для студентов-медиков")

role = 'admin' if is_admin else st.session_state['user_role']

# Сброс теста
if "test_active" not in st.session_state:
    st.session_state.test_active = False
if "test_cases" not in st.session_state:
    st.session_state.test_cases = []
if "test_answers" not in st.session_state:
    st.session_state.test_answers = {}
if "test_start_time" not in st.session_state:
    st.session_state.test_start_time = 0

# --- РЕЖИМ СТУДЕНТА (ТЕСТ) ---
if role == 'student':
    if not st.session_state.test_active:
        st.subheader("🎯 Оценка вашей рыночной стоимости")
        st.write("Выберите желаемую зарплату, и мы проверим, соответствуете ли вы ей. Будет 3 вопроса.")
        
        target_salary = st.slider("Желаемая зарплата (₽)", min_value=40000, max_value=150000, value=80000, step=5000)
        
        category_filter = st.selectbox("Направление", ["Все", "НИИ", "Больницы", "Фарм-маркетинг"])
        cat_db = None if category_filter == "Все" else category_filter
        
        if st.button("Начать собеседование"):
            cases = get_cases_by_salary(target_salary, cat_db)
            if cases:
                st.session_state.test_cases = cases
                st.session_state.test_active = True
                st.session_state.test_answers = {}
                st.session_state.test_target_salary = target_salary
                st.session_state.test_start_time = time.time()
                st.rerun()
            else:
                st.error("Нет кейсов для выбранной категории. Попробуйте другое направление.")
    else:
        # Прохождение теста
        st.subheader(f"Собеседование на {st.session_state.test_target_salary} ₽")
        
        # Находим текущий вопрос (первый, на который нет ответа)
        current_idx = -1
        for i, c in enumerate(st.session_state.test_cases):
            if str(c['id']) not in st.session_state.test_answers:
                current_idx = i
                break
                
        if current_idx != -1:
            c = st.session_state.test_cases[current_idx]
            st.info(f"Вопрос {current_idx + 1} из {len(st.session_state.test_cases)} (Сложность: {c['difficulty']})")
            st.markdown(f"### {c['title']}")
            st.write(c['description'])
            
            ans = st.text_area("Ваш ответ:", key=f"ans_{c['id']}")
            if st.button("Ответить"):
                if ans:
                    # Считаем скорость печати
                    time_spent = time.time() - st.session_state.test_start_time
                    # (Упрощенно, просто сохраняем)
                    st.session_state.test_answers[str(c['id'])] = ans
                    st.session_state.test_start_time = time.time()
                    st.rerun()
                else:
                    st.warning("Напишите ответ!")
        else:
            # Все ответы получены, отправляем на проверку
            st.success("Все ответы получены! Нажмите кнопку ниже для анализа.")
            if st.button("Получить вердикт ИИ"):
                with st.spinner("Анализируем ваши ответы..."):
                    # Формируем запрос
                    qa_text = ""
                    for c in st.session_state.test_cases:
                        qa_text += f"Вопрос: {c['title']}\nЭталон: {c['correct_answer']}\nОтвет студента: {st.session_state.test_answers[str(c['id'])]}\n\n"
                    
                    prompt = f"""
                    Ты — Senior HR и эксперт в фарм/мед индустрии.
                    Студент претендует на зарплату {st.session_state.test_target_salary} рублей.
                    Он ответил на 3 вопроса:
                    
                    {qa_text}
                    
                    Твоя задача:
                    1. Оцени каждый ответ (1-10).
                    2. Сделай вывод: соответствует ли студент заявленной зарплате?
                    3. Дай финальный вердикт по шкале:
                    - Если ответы слабые, предложи зарплату ниже (например, "Реальная стоимость: 60 000 ₽").
                    - Если сильные, предложи выше.
                    - Напиши, что нужно подтянуть, чтобы получить больше.
                    
                    ВАЖНО: Выведи ответ СТРОГО по шаблону:
                    Вердикт: [Одобрено на X / Рекомендуем Y]
                    Фидбек: [твой текст]
                    AI_SUSPECT: [YES/NO]
                    """
                    
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                    payload = {"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": prompt}], "max_tokens": 500, "temperature": 0.1}
                    
                    try:
                        response = requests.post(url, headers=headers, json=payload, timeout=15)
                        response.raise_for_status()
                        response_text = response.json()['choices'][0]['message']['content']
                        
                        verdict_match = re.search(r'Вердикт:\s*(.*?)(?=\n|Фидбек|$)', response_text, re.IGNORECASE)
                        verdict = verdict_match.group(1).strip() if verdict_match else "Не распознан"
                        
                        feedback_match = re.search(r'Фидбек:\s*(.*?)(?=AI_SUSPECT|$)', response_text, re.IGNORECASE | re.DOTALL)
                        feedback = feedback_match.group(1).strip() if feedback_match else "Не удалось."
                        
                        st.success(f"Вердикт: {verdict}")
                        st.info(f"Фидбек: {feedback}")
                        
                        if st.button("Пройти еще раз"):
                            st.session_state.test_active = False
                            st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка: {str(e)}")

# --- РЕЖИМ КОМПАНИИ ---
elif role == 'company':
    tab1, tab2 = st.tabs(["📚 База кейсов", "➕ Предложить кейс"])
    with tab1:
        st.subheader("Опубликованные кейсы")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, description, difficulty, company, category, min_salary FROM cases WHERE status = 'approved'")
        cases = cursor.fetchall()
        conn.close()
        for r in cases:
            st.markdown(f"### {r[1]}")
            st.caption(f"🏷️ {r[5]} | Сложность: {r[3]} | Компания: {r[4]} | ЗП: от {r[6]} ₽")
            st.write(r[2])
            st.divider()
            
    with tab2:
        st.subheader("Добавить кейс")
        with st.form("add_case"):
            new_title = st.text_input("Название")
            new_company = st.text_input("Компания")
            new_category = st.selectbox("Направление", ["НИИ", "Больницы", "Фарм-маркетинг"])
            new_difficulty = st.selectbox("Сложность", ["Легкий", "Средний", "Сложный"])
            new_salary = st.number_input("Мин. зарплата для кейса (₽)", min_value=40000, max_value=150000, value=80000, step=5000)
            new_description = st.text_area("Описание")
            new_correct = st.text_area("Эталонный ответ")
            
            if st.form_submit_button("Отправить"):
                if new_title and new_company:
                    add_case(new_title, new_description, new_difficulty, new_company, new_correct, new_category, new_salary)
                    st.success("Отправлено на модерацию!")
                    time.sleep(1)
                    st.rerun()

# --- РЕЖИМ АДМИНА ---
elif role == 'admin':
    tab1, tab2, tab3 = st.tabs(["📚 Кейсы", "➕ Добавить", "🛡️ Модерация"])
    with tab1:
        st.subheader("Все одобренные кейсы")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, description, difficulty, company, category, min_salary FROM cases WHERE status = 'approved'")
        cases = cursor.fetchall()
        conn.close()
        for r in cases:
            st.markdown(f"### {r[1]}")
            st.caption(f"🏷️ {r[5]} | Сложность: {r[3]} | ЗП: от {r[6]} ₽")
            if st.button(f"Удалить #{r[0]}", key=f"del_{r[0]}"):
                delete_case(r[0])
                st.rerun()
            st.divider()

    with tab2:
        st.subheader("Добавить кейс")
        with st.form("add_case_admin"):
            new_title = st.text_input("Название")
            new_company = st.text_input("Компания")
            new_category = st.selectbox("Направление", ["НИИ", "Больницы", "Фарм-маркетинг"])
            new_difficulty = st.selectbox("Сложность", ["Легкий", "Средний", "Сложный"])
            new_salary = st.number_input("Мин. зарплата (₽)", min_value=40000, max_value=150000, value=80000, step=5000)
            new_description = st.text_area("Описание")
            new_correct = st.text_area("Эталон")
            
            if st.form_submit_button("Опубликовать сразу"):
                if new_title and new_company:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO cases (title, description, difficulty, company, status, correct_answer, category, min_salary) VALUES (%s, %s, %s, %s, 'approved', %s, %s, %s)",
                                   (new_title, new_description, new_difficulty, new_company, new_correct, new_category, new_salary))
                    conn.commit()
                    conn.close()
                    st.success("Кейс добавлен!")
                    time.sleep(1)
                    st.rerun()

    with tab3:
        st.subheader("Модерация")
        pending = get_pending_cases()
        for p in pending:
            st.markdown(f"### {p['title']}")
            st.caption(f"🏷️ {p['category']} | ЗП: от {p['min_salary']} ₽")
            st.write(p['description'])
            col1, col2 = st.columns(2)
            if col1.button(f"✅ Одобрить #{p['id']}"):
                update_case_status(p['id'], 'approved')
                st.rerun()
            if col2.button(f"❌ Удалить #{p['id']}"):
                delete_case(p['id'])
                st.rerun()
            st.divider()
