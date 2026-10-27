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

# СТРОКА ПОДКЛЮЧЕНИЯ К SUPABASE
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
            correct_answer TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_approved_cases():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, difficulty, company, correct_answer FROM cases WHERE status = 'approved'")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "description": r[2], "difficulty": r[3], "company": r[4], "correct_answer": r[5]} for r in rows]

def get_pending_cases():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, difficulty, company, correct_answer FROM cases WHERE status = 'pending'")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "description": r[2], "difficulty": r[3], "company": r[4], "correct_answer": r[5]} for r in rows]

def add_case(title, description, difficulty, company, correct_answer):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cases (title, description, difficulty, company, status, correct_answer) VALUES (%s, %s, %s, %s, 'pending', %s)",
        (title, description, difficulty, company, correct_answer)
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
if admin_pass_input:
    if admin_pass_input == ADMIN_PASSWORD:
        is_admin = True
        st.sidebar.success("✅ Вы вошли как Администратор")
    else:
        st.sidebar.error("❌ Неверный пароль")

# ==========================================
# ИНТЕРФЕЙС
# ==========================================
st.set_page_config(page_title="МедПлатформа", page_icon="🩺")
st.title("🩺 Платформа для студентов-медиков")

if is_admin:
    tab1, tab2, tab3 = st.tabs(["📚 Список кейсов", "➕ Предложить кейс", "🛡️ Модерация"])
else:
    tab1, tab2 = st.tabs(["📚 Список кейсов", "➕ Предложить кейс"])
    tab3 = None

with tab1:
    st.subheader("Доступные кейсы")
    cases = get_approved_cases()
    if cases:
        for case in cases:
            with st.container():
                st.markdown(f"### {case['title']}")
                st.caption(f"Сложность: {case['difficulty']} | Компания: {case['company']}")
                st.write(f"*{case['description']}*")
                
                col1, col2 = st.columns([1, 4])
                with col1:
                    if st.button(f"Решить #{case['id']}", key=f"btn_{case['id']}"):
                        st.session_state['current_case'] = case
                        st.session_state['start_time'] = time.time()
                
                if is_admin:
                    with col2:
                        if st.button(f"❌ Удалить #{case['id']}", key=f"del_approved_{case['id']}"):
                            delete_case(case['id'])
                            st.rerun()
                st.divider()
    else:
        st.info("Пока нет доступных кейсов.")

with tab2:
    st.subheader("Предложить новый кейс")
    st.info("💡 Ваш кейс будет опубликован на платформе только после проверки администратором.")
    
    with st.form("add_case_form"):
        new_title = st.text_input("Название кейса")
        new_company = st.text_input("Компания")
        new_difficulty = st.selectbox("Сложность", ["Легкий", "Средний", "Сложный"])
        new_description = st.text_area("Описание задачи (симптомы)")
        new_correct_answer = st.text_area("Эталонный ответ (правильный диагноз)") # НОВОЕ ПОЛЕ
        
        submit_button = st.form_submit_button("Отправить на модерацию")
        
        if submit_button:
            if new_title and new_company and new_correct_answer:
                add_case(new_title, new_description, new_difficulty, new_company, new_correct_answer)
                st.success("✅ Кейс отправлен на модерацию!")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("Заполните хотя бы название, компанию и эталонный ответ.")

if tab3:
    with tab3:
        st.subheader("Кейсы на модерации")
        pending = get_pending_cases()
        if pending:
            for p_case in pending:
                with st.container():
                    st.markdown(f"### {p_case['title']}")
                    st.caption(f"Компания: {p_case['company']} | Сложность: {p_case['difficulty']}")
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
            st.info("Нет новых кейсов на модерации.")

# ==========================================
# РЕШЕНИЕ КЕЙСА И АНТИПЛАГИАТ
# ==========================================
if 'current_case' in st.session_state:
    case = st.session_state['current_case']
    st.divider()
    st.subheader(f"Решение кейса: {case['title']}")
    
    student_answer = st.text_area("Напиши свой ответ:", height=150, key="student_answer_area")
    
    if st.button("Отправить на проверку ИИ"):
        if student_answer:
            time_spent = time.time() - st.session_state.get('start_time', time.time())
            chars_per_minute = (len(student_answer) / time_spent) * 60 if time_spent > 0 else 9999
            
            with st.spinner("Нейросеть анализирует ответ..."):
                prompt = f"""
                Ты — опытный преподаватель. Твоя задача — оценить ответ студента.
                
                ВАЖНО: НЕ СТАВЬ ДИАГНОЗ САМ. У тебя есть ЭТАЛОННЫЙ ОТВЕТ.
                
                Кейс: "{case['description']}"
                ЭТАЛОННЫЙ ОТВЕТ (Правильный диагноз): "{case['correct_answer']}"
                Ответ студента: "{student_answer}"
                
                Твоя задача:
                1. Сравни ответ студента с эталонным.
                2. Оцени по шкале от 1 до 10 (10 — полностью совпало, 1 — полный бред).
                3. Напиши фидбек (2-3 предложения): угадал ли студент диагноз, и что упустил.
                4. Определи, похож ли текст на ИИ (напиши YES или NO).
                
                ВАЖНО: Выведи ответ СТРОГО по шаблону:
                Оценка: [число]/10
                Фидбек: [твой текст]
                AI_SUSPECT: [YES или NO]
                """
                
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                payload = {"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": prompt}], "max_tokens": 300, "temperature": 0.2}
                
                try:
                    response = requests.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    response_text = response.json()['choices'][0]['message']['content']
                    
                    score_match = re.search(r'Оценка:\s*(\d+)', response_text, re.IGNORECASE)
                    score = score_match.group(1) if score_match else "?"

                    feedback_match = re.search(r'Фидбек:\s*(.*?)(?=AI_SUSPECT|$)', response_text, re.IGNORECASE | re.DOTALL)
                    feedback = feedback_match.group(1).strip() if feedback_match else "Не удалось распознать."

                    ai_suspect = "YES" if "AI_SUSPECT: YES" in response_text.upper().replace(" ", "") else "NO"
                    
                    if score == "?":
                        st.error("⚠️ Нейросеть ответила не по формату. Попробуйте еще раз.")
                        st.code(response_text)
                        st.stop()

                    st.success(f"Оценка: {score}/10")
                    st.info(f"Фидбек от ИИ: {feedback}")
                    
                    if ai_suspect == "YES" and chars_per_minute > 500:
                        st.error(f"🚨 Вердикт: СИЛЬНОЕ ПОДОЗРЕНИЕ НА ИИ. (Скорость ввода: {int(chars_per_minute)} симв/мин).")
                    else:
                        st.success("✅ Вердикт антиплагиата: Чисто.")
                        
                except Exception as e:
                    st.error(f"Ошибка: {str(e)}")
        else:
            st.warning("Напиши ответ!")
