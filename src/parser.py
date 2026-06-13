import time
import json
import re
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from src.logger import info, success, warning, error, note

def load_answers(config: dict) -> dict:
    path = config["advanced"]["answers_file"]
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_answers(config: dict, data: dict):
    path = config["advanced"]["answers_file"]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Extract a stable key from the quiz URL
def quiz_slug(url: str) -> str:
    url = url.rstrip("/")
    slug = url.split("/")[-1]
    info("parser", f"Slug extracted: {slug}")
    return slug

# Block until Cloudflare challenge is gone
def _wait_for_cloudflare(driver: webdriver.Chrome):
    if "just a moment" not in driver.title.lower():
        return
    warning("parser", "Cloudflare challenge detected - complete the verification in the browser")
    note("parser", "Waiting for you to pass the challenge...")
    while "just a moment" in driver.title.lower():
        time.sleep(1)
    success("parser", "Cloudflare challenge passed, resuming...")

# Click Cookies Accept button, only acts once per session
def accept_cookies(driver: webdriver.Chrome, wait: WebDriverWait):
    if getattr(driver, "_cookies_accepted", False):
        return
    try:
        btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.fc-cta-consent")))
        btn.click()
        driver._cookies_accepted = True
        success("parser", "Cookie consent accepted")
    except Exception:
        driver._cookies_accepted = True
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

# Start the quiz, give up, then scrape the answer table that JetPunk reveals after the quiz ends
def parse_quiz(driver: webdriver.Chrome, url: str) -> dict:
    wait = WebDriverWait(driver, 15)
    driver.get(url)
    _wait_for_cloudflare(driver)
    accept_cookies(driver, wait)

    _start_quiz(driver, wait)

    meta = _scrape_meta(driver)

    _give_up(driver, wait)

    answers = _scrape_answers(driver)

    result = {**meta, "url": url, "answers": answers}
    return result

# Log in via API reusing the driver's Cloudflare session cookies
# Injects jpUserHash into the driver and refreshes the page
def _login_api(driver: webdriver.Chrome, config: dict, username: str, password: str) -> bool:
    info("parser", f"Trying to log in as '{username}'...")

    selenium_cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
    info("parser", f"Sending login request ({len(selenium_cookies)} cookies forwarded)")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": config["advanced"]["login_referer"],
        "Origin": "https://www.jetpunk.com",
        "User-Agent": driver.execute_script("return navigator.userAgent"),
    }

    resp = requests.post(
        config["advanced"]["login_api"],
        data={"username": username, "password": password},
        cookies=selenium_cookies,
        headers=headers,
        timeout=10,
    )

    info("parser", f"Login API response: HTTP {resp.status_code}")

    data = resp.json()
    if not data.get("success"):
        error("parser", f"Login failed: {data}")
        return False

    screenname = data.get("obj", {}).get("screenname", username)
    jp_cookie = resp.cookies.get("jpUserHash")

    if not jp_cookie:
        warning("parser", "Login succeeded but jpUserHash cookie not returned")
    else:
        driver.add_cookie({
            "name": "jpUserHash",
            "value": jp_cookie,
            "domain": "www.jetpunk.com",
            "path": "/",
            "secure": True,
        })
        info("parser", "jpUserHash injected into driver")

    driver.refresh()
    _wait_for_cloudflare(driver)
    success("parser", f"Logged in as '{screenname}'")
    return True

# Parse quiz, persist to answers.json, then log in if credentials provided
def fetch_and_cache(driver: webdriver.Chrome, config: dict, url: str, credentials: tuple[str, str] | None = None) -> dict:
    data = load_answers(config)
    slug = quiz_slug(url)

    info("parser", f"Fetching answers for '{slug}'...")
    quiz_data = parse_quiz(driver, url)
    data[slug] = quiz_data
    save_answers(config, data)
    success("parser", f"Cached {len(quiz_data['answers'])} answers for '{slug}'")

    if credentials:
        _login_api(driver, config, *credentials)

    return quiz_data