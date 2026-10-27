import streamlit as st
import psycopg2
import requests
import json
import time
import re  # Регулярные выражения для надежного парсинга

# ==========================================
# НАСТРОЙКИ
# ==========================================
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]
except Exception as e:
    st.error("⚠️ Ошибка: Не настроены секреты GROQ_API_KEY или ADMIN_PASSWORD.")
    st.stop()

# СТРОКА ПОДКЛЮЧЕНИЯ К SUPABASE (ЗАМЕНИ НА СВОЮ)
DB_URI = "postgresql://postgres.dnmxpwggsbyrgqsegmcm:zqE-J4a-3hh-FwL@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

# ==========================================
# РАБОТА С POSTGRESQL (SUPABASE)
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
            status TEXT DEFAULT 'pending'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_approved_cases():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, difficulty, company FROM cases WHERE status = 'approved'")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "description": r[2], "difficulty": r[3], "company": r[4]} for r in rows]

def get_pending_cases():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, difficulty, company FROM cases WHERE status = 'pending'")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "description": r[2], "difficulty": r[3], "company": r[4]} for r in rows]

def add_case(title, description, difficulty, company):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO cases (title, description, difficulty, company, status) VALUES (%s, %s, %s, %s, 'pending')",
        (title, description, difficulty, company)
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
# АВТОРИЗАЦИЯ В САЙДБАРЕ
# ==========================================
st.sidebar.title("Управление")
st.sidebar.caption("Введите пароль для доступа к админ-панели.")
admin_pass_input = st.sidebar.text_input("Пароль администратора", type="password")

is_admin = False
if admin_pass_input:
    if admin_pass_input == ADMIN_PASSWORD:
        is_admin = True
        st.sidebar.success("✅ Вы вошли как Администратор")
    else:
        st.sidebar.error("❌ Неверный пароль")

# ==========================================
# ИНТЕРФЕЙС (ВКЛАДКИ)
# ==========================================
st.set_page_config(page_title="МедПлатформа", page_icon="🩺")
st.title("🩺 Платформа для студентов-медиков")
st.write("Добро пожаловать! Выбери кейс, чтобы начать.")

if is_admin:
    tabs = st.tabs(["📚 Список кейсов", "➕ Предложить кейс", "🛡️ Модерация"])
    tab1, tab2, tab3 = tabs
else:
    tabs = st.tabs(["📚 Список кейсов", "➕ Предложить кейс"])
    tab1, tab2 = tabs
    tab3 = None

# --- ВКЛАДКА 1: СПИСОК КЕЙСОВ ---
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

# --- ВКЛАДКА 2: ПРЕДЛОЖИТЬ КЕЙС ---
with tab2:
    st.subheader("Предложить новый кейс")
    st.info("💡 Ваш кейс будет опубликован на платформе только после проверки администратором.")
    
    with st.form("add_case_form"):
        new_title = st.text_input("Название кейса")
        new_company = st.text_input("Компания (например, Р-Фарм)")
        new_difficulty = st.selectbox("Сложность", ["Легкий", "Средний", "Сложный"])
        new_description = st.text_area("Описание задачи")
        
        submit_button = st.form_submit_button("Отправить на модерацию")
        
        if submit_button:
            if new_title and new_company:
                add_case(new_title, new_description, new_difficulty, new_company)
                st.success("✅ Кейс отправлен на модерацию! Спасибо за вклад.")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("Заполните хотя бы название и компанию.")

# --- ВКЛАДКА 3: МОДЕРАЦИЯ (ТОЛЬКО ДЛЯ АДМИНА) ---
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
# БЛОК РЕШЕНИЯ КЕЙСА И АНТИПЛАГИАТ
# ==========================================
if 'current_case' in st.session_state:
    case = st.session_state['current_case']
    st.divider()
    st.subheader(f"Решение кейса: {case['title']}")
    
    student_answer = st.text_area("Напиши свой ответ (решение проблемы):", height=150, key="student_answer_area")
    
    if st.button("Отправить на проверку ИИ"):
        if student_answer:
            time_spent = time.time() - st.session_state.get('start_time', time.time())
            chars_per_minute = (len(student_answer) / time_spent) * 60 if time_spent > 0 else 9999
            
            with st.spinner("Нейросеть анализирует ответ..."):
                # ЖЕСТКИЙ ПРОМПТ
                prompt = f"""
                Ты — экзаменатор. Оцени ответ студента.
                
                Вопрос (кейс): {case['description']}
                Ответ студента: {student_answer}
                
                Твоя задача:
                1. Поставь оценку от 1 до 10.
                2. Напиши короткий фидбек (2 предложения).
                3. Скажи, писал ли это искусственный интеллект (да или нет).
                
                ВАЖНО: Ты должен ответить СТРОГО в таком формате, без приветствий и лишних слов:
                ОЦЕНКА: [число]
                ФИДБЕК: [твой текст]
                ИИ: [ДА или НЕТ]
                """
                
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": "openai/gpt-oss-20b",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 250,
                    "temperature": 0.1
                }
                
                try:
                    response = requests.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    response_text = response.json()['choices'][0]['message']['content']
                    
                    # Если нейросеть вернула пустоту (такое бывает)
                    if not response_text.strip():
                        st.error("⚠️ Нейросеть вернула пустой ответ. Попробуйте еще раз.")
                        st.stop()
                    
                    # Дебаг: выводим сырой ответ в консоль (чтобы видеть, что она пишет)
                    print("СЫРОЙ ОТВЕТ ИИ:", response_text)
                    
                    # ПАРСИНГ (ищем слова ОЦЕНКА и ФИДБЕК)
                    score = "?"
                    feedback = "Не удалось распознать."
                    ai_suspect = "НЕТ"
                    
                    # Ищем оценку (любую цифру после слова ОЦЕНКА)
                    score_match = re.search(r'ОЦЕНКА:\s*(\d+)', response_text, re.IGNORECASE)
                    if score_match:
                        score = score_match.group(1)
                        
                    # Ищем фидбек (текст после слова ФИДБЕК)
                    feedback_match = re.search(r'ФИДБЕК:\s*(.*?)(?=ИИ:|$)', response_text, re.IGNORECASE | re.DOTALL)
                    if feedback_match:
                        feedback = feedback_match.group(1).strip()
                        
                    # Ищем проверку на ИИ
                    if "ИИ: ДА" in response_text.upper():
                        ai_suspect = "YES"
                    
                    # Если оценку не нашли — выводим сырой ответ для отладки
                    if score == "?":
                        st.error("⚠️ Нейросеть ответила не по формату. Вот что она написала:")
                        st.code(response_text)
                        st.stop()

                    st.success(f"Оценка: {score}/10")
                    st.info(f"Фидбек от ИИ: {feedback}")
                    
                    # ЛОГИКА МЕТА-АНАЛИЗА
                    if ai_suspect == "YES":
                        if chars_per_minute > 500:
                            st.error(f"🚨 Вердикт: СИЛЬНОЕ ПОДОЗРЕНИЕ НА ИИ. (Скорость: {int(chars_per_minute)} симв/мин).")
                        else:
                            st.success("✅ Вердикт антиплагиата: Чисто.")
                    else:
                        st.success("✅ Вердикт антиплагиата: Чисто.")
                        
                except Exception as e:
                    st.error(f"Ошибка при обращении к нейросети: {str(e)}")
        else:
            st.warning("Напиши хоть что-нибудь!")
