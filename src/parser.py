import time
import json
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from src.logger import info, success, warning, error

ANSWERS_FILE = "answers.json"

def load_answers() -> dict:
    try:
        with open(ANSWERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_answers(data: dict):
    with open(ANSWERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Extract a stable key from the quiz URL
def quiz_slug(url: str) -> str:
    url = url.rstrip("/")
    slug = url.split("/")[-1]
    info("parser", f"Slug extracted: {slug}")
    return slug

# Start the quiz, give up, then scrape the answer table that JetPunk reveals after the quiz ends
def parse_quiz(driver: webdriver.Chrome, url: str) -> dict:
    wait = WebDriverWait(driver, 15)
    driver.get(url)
    accept_cookies(driver, wait)

    _start_quiz(driver, wait)

    meta = _scrape_meta(driver)

    _give_up(driver, wait)

    answers = _scrape_answers(driver)

    result = {**meta, "url": url, "answers": answers}
    return result

# Scrape quiz metadata
def _scrape_meta(driver: webdriver.Chrome) -> dict:
    meta = {}

    meta["title"] = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
    meta["instructions"] = driver.find_element(By.CSS_SELECTOR, ".instructions").text.strip()

    score_text = driver.find_element(By.CSS_SELECTOR, "#current-score").text
    meta["total_answers"] = int(re.findall(r"\d+", score_text)[1])

    timer_text = driver.find_element(By.CSS_SELECTOR, ".timer").text.strip()
    minutes, seconds = map(int, timer_text.split(":"))
    meta["time_limit"] = ((minutes * 60 + seconds + 5) // 6) * 6

    return meta

# Click Cookies Accept button
def accept_cookies(driver: webdriver.Chrome, wait: WebDriverWait):
    try:
        btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.fc-cta-consent")))
        btn.click()
        success("parser", "Cookie consent accepted")
    except Exception:
        info("parser", "No cookie popup detected, continuing...")

# Click Start button
def _start_quiz(driver: webdriver.Chrome, wait: WebDriverWait):
    btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button#start-button, button.start-button, #play-button")))
    btn.click()

# Click Giveup button to reveal answers
def _give_up(driver: webdriver.Chrome, wait: WebDriverWait):
    btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.give-up")))
    btn.click()
    time.sleep(1)

# Find the answer input box
def _find_input(driver: webdriver.Chrome, wait: WebDriverWait):
    return wait.until(EC.presence_of_element_located((By.ID, "txt-answer-box")))

# Scrape the answer list revealed after the quiz ends
def _scrape_answers(driver: webdriver.Chrome) -> list[str]:
    elements = driver.find_elements(By.CSS_SELECTOR, "td.answer-display")
    answers = [el.text.strip() for el in elements if el.text.strip()]

    seen = set()
    unique = []
    for a in answers:
        key = a.lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)

    return unique

# Parse quiz and persist to answers.json
def fetch_and_cache(driver: webdriver.Chrome, url: str) -> dict:
    data = load_answers()
    slug = quiz_slug(url)

    info("parser", f"Fetching answers for '{slug}'...")
    quiz_data = parse_quiz(driver, url)
    data[slug] = quiz_data
    save_answers(data)
    success("parser", f"Cached {len(quiz_data['answers'])} answers for '{slug}'")
    return quiz_data