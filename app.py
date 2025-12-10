import streamlit as st
import pandas as pd
import io
from datetime import datetime
from scraper import get_google_maps_data

st.set_page_config(page_title="Google Maps Scraper", layout="wide")

st.markdown("""
<style>
    .stButton>button {width: 100%;}
</style>
""", unsafe_allow_html=True)

st.title("Google Maps Scraper")

# Ініціалізуємо історію пошуків
# Зберігаємо всі результати і поточний активний пошук
if 'history' not in st.session_state:
    st.session_state.history = {}  # тут будуть всі збережені пошуки
if 'active_key' not in st.session_state:
    st.session_state.active_key = None  # який пошук зараз відкритий

# бокова панель
with st.sidebar:
    # форма для налаштувань пошуку
    with st.form("settings_form"):
        st.header("Налаштування пошуку")
        city = st.text_input("Місто", "Львів")
        obj_name = st.text_input("Що шукаємо?", "Кав'ярні")
        limit = st.slider("Кількість результатів", 5, 100, 20)

        st.header("Налаштування драйвера")
        threads = st.slider("Потоки", 1, 5, 3)
        headless_mode = st.checkbox("Headless режим", value=True)
        show_powershell = st.checkbox("Відкрити PowerShell з логами", value=False)

        submit_button = st.form_submit_button("Почати збір даних", type="primary")

    st.header("Історія пошуків")

    # якщо в історії щось є, показуємо список результатів
    if st.session_state.history:
        keys = list(st.session_state.history.keys())[::-1]  # нові зверху
        selected_search = st.selectbox(
            "Виберіть результат:",
            options=keys,
            key="history_selector"  # зв’язуємо selectbox з логікою нижче
        )

        # кнопка для очищення всієї історії
        if st.button("Очистити історію"):
            st.session_state.history = {}
            st.session_state.active_key = None
            st.rerun()
    else:
        st.info("Історія поки порожня")

# обробка нового пошуку
if submit_button:
    if city and obj_name:
        with st.spinner(f"Збираю дані: {obj_name} у м. {city}..."):
            # виклик скрапера, отримуємо таблицю і логи
            new_df, new_logs = get_google_maps_data(
                obj_name, city, limit, threads, headless_mode, show_powershell)

            if not new_df.empty:
                # створюємо унікальну назву для збереження в історії
                time_str = datetime.now().strftime("%H:%M:%S")
                history_key = f"{obj_name} - {city} ({time_str})"

                # зберігаємо результат у словник історії
                st.session_state.history[history_key] = {
                    'df': new_df,
                    'logs': new_logs
                }

                # встановлюємо цей результат як активний
                st.session_state.active_key = history_key
                st.session_state.message = f"Знайдено {len(new_df)} записів! Додано в історію."

                if 'message' in st.session_state:
                    st.success(st.session_state.message)
                # del st.session_state.message

                # оновлюємо selectbox, щоб показав новий результат
                st.rerun()
            else:
                st.error("Нічого не знайдено.")
    else:
        st.warning("Введіть дані для пошуку.")

# відображення вибраного результату
current_key = st.session_state.get("history_selector")

if current_key and current_key in st.session_state.history:
    data_entry = st.session_state.history[current_key]
    df = data_entry['df']
    logs = data_entry['logs']

    st.subheader(f"Результат: {current_key}")

    # вкладка з логами
    with st.expander("Системний журнал (Logs)", expanded=False):
        st.code("\n".join(logs), language="log")

    tab1, tab2 = st.tabs(["Таблиця даних", "Аналітика"])

    with tab1:
        # вибираємо тільки ті колонки, які реально є
        cols = ["Назва", "Рейтинг", "Відгуки", "Адреса", "Номер телефону", "Вебсайт"]
        final_cols = [c for c in cols if c in df.columns]
        st.dataframe(df[final_cols], use_container_width=True)

        # кнопки для скачування даних
        file_prefix = current_key.replace(":", "-").replace(" ", "_")
        col1, col2 = st.columns(2)
        with col1:
            csv = df[final_cols].to_csv(index=False).encode('utf-8')
            st.download_button("Скачати CSV", csv, f"{file_prefix}.csv", "text/csv")
        with col2:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df[final_cols].to_excel(writer, index=False)
            st.download_button("Скачати Excel", buffer,
                               f"{file_prefix}.xlsx", "application/vnd.ms-excel")

    with tab2:
        # графіки та аналітика
        chart_df = df.copy()
        if "Рейтинг" in chart_df.columns:
            chart_df["Rate_Num"] = pd.to_numeric(
                chart_df["Рейтинг"].astype(str).str.extract(
                    r'(\d+[.,]\d+)')[0].str.replace(',', '.'),
                errors='coerce'
            )
            valid_data = chart_df[chart_df["Rate_Num"] > 0]
            if not valid_data.empty:
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.bar_chart(valid_data["Rate_Num"].value_counts().sort_index())
                with c2:
                    st.metric("Середній рейтинг", f"{valid_data['Rate_Num'].mean():.2f}")
            else:
                st.info("Мало даних для графіка.")
