import time
import re
import random
import datetime
import pandas as pd
import subprocess
import os
from concurrent.futures import ThreadPoolExecutor
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

execution_logs = []
LOG_FILE = "live_logs.txt"

# функція для запису логів у список і файл
def log(message):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    execution_logs.append(entry)
    print(entry)

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except Exception:
        pass

# функція для створення драйвера браузера
def get_driver(is_headless=False):
    options = webdriver.ChromeOptions()
    if is_headless:
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1080,1920")
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    options.add_argument(f"user-agent={user_agent}")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("--lang=uk")
    options.add_argument("--log-level=3")
    options.page_load_strategy = 'eager'

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    # driver.set_page_load_timeout(20)
    return driver

def check_city_exists(driver, city_name):
    driver.get(f"https://www.google.com/maps/search/{city_name}")
    try:
        WebDriverWait(driver, 5).until(EC.url_contains("/place/"))
        return True
    except TimeoutException:
        log(f"Місто '{city_name}' не знайдено.")
        return False

# функція для обробки групи посилань
def scrape_batch(urls, is_headless=False, thread_id=1, external_driver=None):
    # Якщо передали зовнішній драйвер (для 1 потоку), використовуємо його
    if external_driver:
        driver = external_driver
        owns_driver = False  # Прапор, що цей драйвер не треба закривати тут
    else:
        driver = get_driver(is_headless)
        owns_driver = True

    batch_data = []
    log(f"Thread-{thread_id}: старт роботи. Посилань: {len(urls)}")

    try:
        for url in urls:
            try:
                driver.get(url)
            except TimeoutException:
                driver.execute_script("window.stop();")
            except Exception as e:
                if "out of memory" in str(e).lower() or "timed out receiving" in str(e).lower():
                    log(f"Thread-{thread_id}: зависання браузера, перезапускаю")
                    try:
                        driver.quit()
                    except:
                        pass
                    time.sleep(2)
                    # Тут ми змушені створити новий, навіть якщо був external_driver, бо старий "помер"
                    driver = get_driver(is_headless)
                    owns_driver = True  # Тепер ми власники нового драйвера
                    continue
                else:
                    log(f"Thread-{thread_id}: не вдалося відкрити сторінку: {e}")
                    continue

            # time.sleep(random.uniform(1.0, 2.0))

            # намагаємося взяти назву об'єкта
            try:
                name_elem = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
                name = name_elem.text
            except:
                name = "Без назви"

            if not name or name.strip() == "" or name == "Без назви":
                log(f"Thread-{thread_id}: пропускаю — немає назви")
                continue

            # намагаємося взяти рейтинг і кількість відгуків
            rating_text, reviews_text = "", ""
            try:
                rating_div = WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div.F7nice'))
                )
                full_text = rating_div.get_attribute('textContent')

                matches = re.findall(r'(\d+[.,]?\d*)', full_text)
                if matches:
                    rating_text = matches[0].replace('.', ',')

                review_match = re.search(r'\((.*?)\)', full_text)
                if review_match:
                    reviews_text = review_match.group(1).replace(
                        ' ', '').replace(u'\xa0', '')  # чистка пробілів
            except:
                pass

            # намагаємося взяти категорію
            category = ""
            try:
                cat_btn = driver.find_element(
                    By.CSS_SELECTOR, 'button[jsaction*="category"]'
                )
                category = cat_btn.text
            except:
                pass

            # збираємо адресу, телефон і сайт
            address, phone, website = "", "", ""
            try:
                WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-item-id]'))
                )
            except:
                pass

            actions = driver.find_elements(By.CSS_SELECTOR, '[data-item-id]')
            for btn in actions:
                item_id = btn.get_attribute('data-item-id')
                text = btn.text
                if not item_id:
                    continue
                if item_id == "address":
                    raw_addr = text.replace('\n', ', ').replace('', '').strip()
                    address = f"{category} {raw_addr}" if category else raw_addr
                elif item_id.startswith("phone:"):
                    phone = item_id.replace("phone:", "").replace("tel:", "").strip()
                elif item_id == "authority":
                    website = btn.get_attribute('href') or text

            if not address:
                try:
                    addr_elem = driver.find_element(
                        By.CSS_SELECTOR, 'button[data-item-id*="address"]'
                    )
                    address = addr_elem.get_attribute(
                        "aria-label").replace("Адреса: ", "")
                except:
                    pass

            log(f"Thread-{thread_id}: {name}")
            batch_data.append({
                "Назва": name,
                "Рейтинг": rating_text,
                "Відгуки": reviews_text,
                "Адреса": address,
                "Номер тел": phone,
                "Вебсайт": website
            })

    finally:
        log(f"Thread-{thread_id}: роботу завершено")
        # Закриваємо драйвер ТІЛЬКИ якщо ми його створювали всередині цієї функції
        if owns_driver:
            driver.quit()

    return batch_data

# основна функція для збору даних з Google Maps
def get_google_maps_data(target_object, target_city, max_results=10, num_threads=1, is_headless=False, show_console=False):
    start_time = time.time()
    execution_logs.clear()

    # очищаємо файл логів перед стартом
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("Start scraping\n")

    # якщо потрібен живий перегляд логів у PowerShell
    if show_console:
        try:
            cmd = f'start powershell -NoExit -Command "Get-Content -Path \'{LOG_FILE}\' -Wait -Encoding UTF8"'
            subprocess.Popen(cmd, shell=True)
        except Exception as e:
            log(f"Не вдалося відкрити PowerShell: {e}")

    log(f"Параметри пошуку: '{target_object}' у '{target_city}'")

    driver = get_driver(is_headless)
    if not check_city_exists(driver, target_city):
        driver.quit()
        return pd.DataFrame(), execution_logs
    links_to_visit = []

    try:
        log(f"Відкриваю місто: '{target_city}'")
        driver.get(f"https://www.google.com/maps/search/{target_city}")

        wait = WebDriverWait(driver, 15)
        search_box = wait.until(EC.element_to_be_clickable((By.ID, "searchboxinput")))
        driver.execute_script("arguments[0].value = '';", search_box)

        log(f"Вводжу запит: '{target_object}'")
        search_box.send_keys(target_object)
        search_box.send_keys(Keys.ENTER)

        try:
            wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'div[role="feed"]')))
        except TimeoutException:
            log("Список не завантажився. Перевіряю наявність помилки пошуку.")

            page_source = driver.page_source
            if "Google Карти не можуть знайти" in page_source or "Google Maps can't find" in page_source:
                log(f"За запитом '{target_object}' нічого не знайдено.")
                driver.quit()
                return pd.DataFrame(), execution_logs

            try:
                search_btn = driver.find_element(By.ID, "searchbox-searchbutton")
                search_btn.click()
                time.sleep(3)
                if len(driver.find_elements(By.CSS_SELECTOR, 'div[role="feed"]')) == 0:
                    driver.quit()
                    return pd.DataFrame(), execution_logs
            except:
                log(f"За запитом '{target_object}' нічого не знайдено.")
                driver.quit()
                return pd.DataFrame(), execution_logs

        scrollable_div = driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
        previous_cnt = 0
        while len(links_to_visit) < max_results:
            elements = driver.find_elements(By.CSS_SELECTOR, 'a.hfpxzc')
            for elem in elements:
                url = elem.get_attribute('href')
                if url and url not in links_to_visit:
                    links_to_visit.append(url)

            if len(links_to_visit) >= max_results:
                break

            if len(elements) == previous_cnt and len(elements) > 0:
                time.sleep(2)
                new_elems = driver.find_elements(By.CSS_SELECTOR, 'a.hfpxzc')
                if len(new_elems) == previous_cnt:
                    break

            previous_cnt = len(elements)
            driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollHeight", scrollable_div)
            time.sleep(1.5)

        links_to_visit = links_to_visit[:max_results]
        log(f"Зібрано посилань: {len(links_to_visit)}")

    except Exception as e:
        log(f"Критична помилка: {e}")
        driver.quit()
        return pd.DataFrame(), execution_logs

    if not links_to_visit:
        log("Немає посилань для обробки")
        driver.quit()
        return pd.DataFrame(), execution_logs

    final_results = []

    if num_threads == 1:
        log("Режим одного потоку")
        final_results = scrape_batch(
            links_to_visit, is_headless, 1, external_driver=driver)
        driver.quit()
    else:
        log("Режим багатьох потоків")
        driver.quit()

        chunk_size = (len(links_to_visit) + num_threads - 1) // num_threads
        chunks = [links_to_visit[i:i + chunk_size]
                  for i in range(0, len(links_to_visit), chunk_size)]

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = []
            for i, chunk in enumerate(chunks):
                futures.append(executor.submit(scrape_batch, chunk, is_headless, i + 1))
            for future in futures:
                final_results.extend(future.result())

    duration = time.time() - start_time
    log(f"Загальний час виконання: {duration:.2f} сек")

    return pd.DataFrame(final_results), execution_logs
