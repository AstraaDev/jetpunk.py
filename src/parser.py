import time
import json
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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

    print(f"[parser] Extracting slug from URL. Slug : {slug}")
    return slug

# Start the quiz, give up, then scrape the answer table that JetPunk reveals after the quiz ends
def parse_quiz(driver: webdriver.Chrome, url: str) -> dict:
    wait = WebDriverWait(driver, 15)
    driver.get(url)
    accept_cookies(driver, wait)

    # Start the quiz
    _start_quiz(driver, wait)

    # Collect metadata from the page
    meta = _scrape_meta(driver)

    # Give Up to reveal answers
    _give_up(driver, wait)

    # Scrape the answer table
    answers = _scrape_answers(driver)

    result = {**meta, "url": url, "answers": answers}
    return result

# Scrape quiz metadata
def _scrape_meta(driver: webdriver.Chrome) -> dict:
    meta = {}

    # Title
    meta["title"] = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()

    # Instructions
    meta["instructions"] = driver.find_element(By.CSS_SELECTOR, ".instructions").text.strip()

    # Number of expected answers
    score_text = driver.find_element(By.CSS_SELECTOR, "#current-score").text
    meta["total_answers"] = int(re.findall(r"\d+", score_text)[1])

    # Time limit
    timer_text = driver.find_element(By.CSS_SELECTOR, ".timer").text.strip()
    minutes, seconds = map(int, timer_text.split(":"))
    meta["time_limit"] = ((minutes * 60 + seconds + 5) // 6) * 6

    return meta

# Click Cookies Accept button
def accept_cookies(driver: webdriver.Chrome, wait: WebDriverWait):
    btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.fc-cta-consent")))
    btn.click()

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

    # Deduplicate answers while preserving order
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

    print(f"[parser] Fetching answers for '{slug}'...")
    quiz_data = parse_quiz(driver, url)
    data[slug] = quiz_data
    save_answers(data)
    print(f"[parser] Cached {len(quiz_data['answers'])} answers for '{slug}'")
    return quiz_data
