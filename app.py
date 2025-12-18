import streamlit as st
import pandas as pd
import io
import re
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
if 'message' not in st.session_state:
    st.session_state.message = None

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
        keys = list(st.session_state.history.keys())[::-1]
        index = 0
        if st.session_state.active_key in keys:
            index = keys.index(st.session_state.active_key)

        selected_search = st.selectbox(
            "Виберіть результат:",
            options=keys,
            index=index,
            key="history_selector"
        )

        # Оновлюємо активний ключ при ручному виборі
        if selected_search != st.session_state.active_key:
            st.session_state.active_key = selected_search
            st.rerun()

        if st.button("Очистити історію"):
            st.session_state.history = {}
            st.session_state.active_key = None
            st.session_state.message = None
            st.rerun()
    else:
        st.info("Історія поки порожня")

# обробка нового пошуку
if submit_button:
    if city and obj_name:
        with st.spinner(f"Збираю дані: {obj_name} у м. {city}."):
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
                st.rerun()
            else:
                st.error("Нічого не знайдено.")
                with st.expander("Деталі пошуку (Logs)", expanded=True):
                    st.code("\n".join(new_logs), language="log")
    else:
        st.warning("Введіть дані для пошуку.")

# Відображення повідомлення про успіх (одноразово)
if st.session_state.message:
    st.success(st.session_state.message)
    st.session_state.message = None  # Очищаємо, щоб не висіло вічно

current_key = st.session_state.get("active_key")

if current_key and current_key in st.session_state.history:
    data_entry = st.session_state.history[current_key]
    df = data_entry['df']
    logs = data_entry['logs']

    st.subheader(f"Результат: {current_key}")

    # вкладка з логами
    with st.expander("Системний журнал (Logs)", expanded=False):
        st.code("\n".join(logs), language="log")

    view_mode = st.radio(
        "Режим перегляду:",
        ["Таблиця даних", "Аналітика"],
        horizontal=True,
        key="view_mode_radio"
    )

    if view_mode == "Таблиця даних":
        display_df = df.copy()
        if "Відгуки" in display_df.columns:
            display_df["Відгуки"] = (
                display_df["Відгуки"].astype(str).str.replace(r'\D', '', regex=True)
                .replace('', '0').fillna('0').astype(int)
            )

        if "Рейтинг" in display_df.columns:
            display_df["Рейтинг"] = (
                display_df["Рейтинг"].astype(str).str.extract(r'(\d+[.,]?\d*)')[0]
                .str.replace(',', '.').fillna('0.0').astype(float)
            )

        cols = ["Назва", "Рейтинг", "Відгуки", "Адреса", "Номер тел", "Вебсайт"]
        final_cols = [c for c in cols if c in display_df.columns]
        st.dataframe(
            display_df[final_cols],
            width='stretch',
            column_config={
                "Вебсайт": st.column_config.LinkColumn(),
            }
        )

        # кнопки для скачування даних
        file_prefix = current_key.replace(":", "-").replace(" ", "")

        csv = df[final_cols].to_csv(index=False).encode('utf-8')
        st.download_button("Скачати CSV", csv, f"{file_prefix}.csv", "text/csv")

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            display_df[final_cols].to_excel(writer, index=False)
        st.download_button("Скачати Excel", buffer,
                           f"{file_prefix}.xlsx", "application/vnd.ms-excel")

    elif view_mode == "Аналітика":
        chart_df = df.copy()

        # Обробка для графіків
        if "Відгуки" in chart_df.columns:
            chart_df["Відгуки"] = (
                chart_df["Відгуки"].astype(str).str.replace(r'\D', '', regex=True)
                .replace('', '0').fillna('0').astype(int)
            )
        if "Рейтинг" in chart_df.columns:
            chart_df["Рейтинг"] = (
                chart_df["Рейтинг"].astype(str).str.extract(r'(\d+[.,]?\d*)')[0]
                .str.replace(',', '.').fillna('0.0').astype(float)
            )

        st.subheader("Аналітика рейтингів")
        if "Рейтинг" in chart_df.columns:
            valid_rating = chart_df[chart_df["Рейтинг"] > 0]
            if not valid_rating.empty:
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.bar_chart(valid_rating["Рейтинг"].value_counts().sort_index())
                with c2:
                    st.metric("Середній рейтинг",
                              f"{valid_rating['Рейтинг'].mean():.2f}")
                    st.metric("Кількість закладів", f"{len(valid_rating)}")
            else:
                st.info("Мало даних для графіка.")

        st.divider()

        st.subheader("Аналітика відгуків")
        if "Відгуки" in chart_df.columns:
            valid_reviews = chart_df[chart_df["Відгуки"] > 0]
        else:
            valid_reviews = pd.DataFrame()

        if not valid_reviews.empty:
            total_rev = valid_reviews["Відгуки"].sum()
            avg_rev = valid_reviews["Відгуки"].mean()

            c1, c2 = st.columns([4, 1])

            with c1:
                sorted_reviews = valid_reviews.sort_values("Відгуки", ascending=False)
                total_items = len(sorted_reviews)
                items_per_page = 10

                # Слайдер
                if total_items > items_per_page:
                    start_rank = st.select_slider(
                        "Виберіть топ місць:",
                        options=range(1, total_items + 1, items_per_page),
                        format_func=lambda x: f"Місця {x}-{min(x + items_per_page - 1, total_items)}",
                        key="analytics_slider_fix"
                    )
                else:
                    start_rank = 1

                start_idx = start_rank - 1
                end_idx = start_idx + items_per_page
                page_data = sorted_reviews.iloc[start_idx:end_idx]

                st.bar_chart(page_data.set_index("Назва")["Відгуки"])

            with c2:
                st.metric("Всього відгуків", f"{total_rev:,}".replace(",", " "))
                st.metric("Середнє на заклад", f"{int(avg_rev)}")
        else:
            st.info("Мало даних для графіка.")
