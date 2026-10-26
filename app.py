import streamlit as st
import sqlite3
import requests
import json

# ==========================================
# НАСТРОЙКИ (ВСТАВЬ СВОЙ КЛЮЧ ОТ GROQ)
# ==========================================
GROQ_API_KEY = "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"

# ==========================================
# РАБОТА С БАЗОЙ ДАННЫХ
# ==========================================
def get_db_connection():
    conn = sqlite3.connect("platform.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            difficulty TEXT,
            company TEXT
        )
    ''')
    # Добавляем тестовый кейс, если база пустая
    cursor.execute("SELECT COUNT(*) FROM cases")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO cases (title, description, difficulty, company) VALUES (?, ?, ?, ?)", 
                       ("Кейс от Р-Фарм: Оптимизация поставок", "Сократить логистические издержки на 15%", "Средний", "Р-Фарм"))
        conn.commit()
    conn.close()

init_db()

def get_all_cases():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, difficulty, company FROM cases")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_case(title, description, difficulty, company):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cases (title, description, difficulty, company) VALUES (?, ?, ?, ?)",
        (title, description, difficulty, company)
    )
    conn.commit()
    conn.close()

# ==========================================
# ИНТЕРФЕЙС САЙТА
# ==========================================
st.set_page_config(page_title="МедПлатформа", page_icon="🩺")
st.title("🩺 Платформа для студентов-медиков")
st.write("Добро пожаловать! Выбери кейс, чтобы начать.")

tab1, tab2 = st.tabs(["📚 Список кейсов", "➕ Добавить кейс"])

with tab1:
    cases = get_all_cases()
    if cases:
        for case in cases:
            with st.container():
                st.markdown(f"### {case['title']}")
                st.caption(f"Сложность: {case['difficulty']} | Компания: {case['company']}")
                st.write(f"*{case['description']}*")
                
                if st.button(f"Решить кейс #{case['id']}", key=f"btn_{case['id']}"):
                    st.session_state['current_case'] = case
                st.divider()
    else:
        st.info("Пока нет доступных кейсов.")

with tab2:
    st.subheader("Добавить новый кейс от компании")
    with st.form("add_case_form"):
        new_title = st.text_input("Название кейса")
        new_company = st.text_input("Компания (например, Р-Фарм)")
        new_difficulty = st.selectbox("Сложность", ["Легкий", "Средний", "Сложный"])
        new_description = st.text_area("Описание задачи")
        
        submit_button = st.form_submit_button("Опубликовать кейс")
        
        if submit_button:
            if new_title and new_company:
                add_case(new_title, new_description, new_difficulty, new_company)
                st.success("✅ Кейс успешно добавлен! Перейдите во вкладку 'Список кейсов'.")
                st.rerun()
            else:
                st.warning("Заполните хотя бы название и компанию.")

# ==========================================
# БЛОК РЕШЕНИЯ КЕЙСА И ИИ
# ==========================================
if 'current_case' in st.session_state:
    case = st.session_state['current_case']
    st.divider()
    st.subheader(f"Решение кейса: {case['title']}")
    
    student_answer = st.text_area("Напиши свой ответ (решение проблемы):", height=150)
    
    if st.button("Отправить на проверку ИИ"):
        if student_answer:
            with st.spinner("Нейросеть думает..."):
                prompt = f"""
                Ты — опытный преподаватель и эксперт в области фармакологии и менеджмента.
                Студент решает следующий кейс:
                "{case['description']}"
                
                Ответ студента:
                "{student_answer}"
                
                Оцени ответ по шкале от 1 до 10. Будь строгим, но справедливым. 
                Дай краткий фидбек (2-3 предложения): что сделано хорошо, а что упущено.
                
                ВАЖНО: Выведи ответ СТРОГО в таком формате, без лишних слов:
                Оценка: [число]/10
                Фидбек: [твой текст]
                """
                
                # Запрос к Groq
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "openai/gpt-oss-20b",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.2
                }
                
                try:
                    # В облаке прокси не нужен, Groq работает напрямую
                    response = requests.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    
                    response_data = response.json()
                    response_text = response_data['choices'][0]['message']['content']
                    
                    score = "Не распознана"
                    feedback = response_text
                    
                    lines = response_text.strip().split("\n")
                    for line in lines:
                        if "Оценка:" in line:
                            score = line.split("Оценка:")[1].split("/")[0].strip()
                        elif "Фидбек:" in line:
                            feedback = line.replace("Фидбек:", "").strip()
                    
                    if "Фидбек:" in response_text:
                        feedback = response_text.split("Фидбек:")[1].strip()
                        
                    st.success(f"Оценка: {score}/10")
                    st.info(f"Фидбек от ИИ: {feedback}")
                    
                except Exception as e:
                    st.error(f"Ошибка нейросети: {str(e)}")
        else:
            st.warning("Напиши хоть что-нибудь!")