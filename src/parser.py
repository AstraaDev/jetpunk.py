import time
import json
import re
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from src.logger import info, success, warning, error, note

# Raised when the quiz type/layout cannot be parsed
class UnsupportedQuizError(Exception):
    pass

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

# Scrape the answer list for image quizzes
def _scrape_image_answers(driver: webdriver.Chrome) -> dict:
    grid = driver.find_element(By.ID, "photo-grid")

    photo_holders = grid.find_elements(By.CSS_SELECTOR, "div.photo-holder")
    answers = {}

    for holder in photo_holders:
        holder_class = holder.get_attribute("class")
        # Extract the ID from "scroll-target-..."
        target_id = next((c.replace("scroll-target-", "") for c in holder_class.split() if c.startswith("scroll-target-")), None)
        if not target_id:
            continue

        img_src = holder.find_element(By.TAG_NAME, "img").get_attribute("src")
        answer_el = grid.find_element(By.CSS_SELECTOR, f"div.answer-display.answer-{target_id}")
        answers[img_src] = answer_el.text.strip()

    return answers


# Detect quiz type from the "similar quizzes by tag" box
def _detect_quiz_type(driver: webdriver.Chrome) -> str:
    try:
        tags_box = driver.find_element(By.ID, "tags-for-quiz")
        links = tags_box.find_elements(By.TAG_NAME, "a")
        for link in links:
            href = link.get_attribute("href") or ""
            if "/tags/picture" in href or "/tags/par-images" in href:
                return "image"
            if "/tags/sudden-death" in href or "/tags/mort-subite" in href:
                return "sudden_death"
            if "/tags/fill-in-the-map" in href or "/tags/carte-quiz" in href or "/tags/map" in href:
                return "map"
    except Exception:
        pass
    return "text"

# Scrape quiz metadata
def _scrape_meta(driver: webdriver.Chrome) -> dict:
    meta = {}

    meta["type"] = _detect_quiz_type(driver)
    info("parser", f"Quiz type detected: {meta['type']}")

    meta["title"] = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
    meta["instructions"] = driver.find_element(By.CSS_SELECTOR, ".instructions").text.strip()

    if meta["type"] in ("map", "sudden_death"):
        remaining = int(driver.find_element(By.ID, "num-remaining").text.strip())
        guessed   = int(driver.find_element(By.ID, "num-guessed").text.strip())
        meta["total_answers"] = remaining + guessed
    else:
        score_text = driver.find_element(By.CSS_SELECTOR, "#current-score").text
        matches = re.findall(r"\d+", score_text)
        if len(matches) < 2:
            meta["type"] = "unknown"
            raise UnsupportedQuizError(f"unable to read score format (detected type: {meta['type']})")
        meta["total_answers"] = int(matches[1])

    timer_text = driver.find_element(By.CSS_SELECTOR, ".timer").text.strip()
    minutes, seconds = map(int, timer_text.split(":"))
    meta["time_limit"] = ((minutes * 60 + seconds + 5) // 6) * 6

    return meta

# Scrape the answer map for map quizzes
def _scrape_map_answers(driver: webdriver.Chrome, wait: WebDriverWait, total: int) -> dict:
    answers = {}
    for _ in range(total):
        try:
            path = driver.find_element(By.CSS_SELECTOR, "path.map-highlight")
            country_id = path.get_attribute("id")
            label = driver.find_element(By.CSS_SELECTOR, "div.map-post-game-correct").text.strip()
            if country_id and label:
                answers[country_id] = label
        except Exception:
            pass
        try:
            btn = next(b for b in driver.find_elements(By.CSS_SELECTOR, "button.map-highlight-next") if b.is_displayed())
            btn.click()
        except Exception:
            break
    return answers

# Scrape the answer grid for sudden death quizzes
def _scrape_sudden_death_answers(driver: webdriver.Chrome) -> list[str]:
    items = driver.find_elements(By.CSS_SELECTOR, "div.grid-item.green-outline")
    return [item.get_attribute("data-id") for item in items if item.get_attribute("data-id")]

# Start the quiz, give up, then scrape the answer table that JetPunk reveals after the quiz ends
def parse_quiz(driver: webdriver.Chrome, url: str) -> dict:
    wait = WebDriverWait(driver, 15)
    driver.get(url)
    accept_cookies(driver, wait)

    driver.refresh()
    _wait_for_cloudflare(driver)

    _start_quiz(driver, wait)

    meta = _scrape_meta(driver)

    _give_up(driver, wait)

    if meta["type"] == "image":
        answers = _scrape_image_answers(driver)
    elif meta["type"] == "map":
        answers = _scrape_map_answers(driver, wait, meta["total_answers"])
    elif meta["type"] == "sudden_death":
        answers = _scrape_sudden_death_answers(driver)
    else:
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

# Scrape the quiz, merge results into the cache
def fetch_and_cache(driver: webdriver.Chrome, config: dict, url: str, credentials: tuple[str, str] | None = None, refresh: bool = False) -> dict:
    data = load_answers(config)
    slug = quiz_slug(url)

    info("parser", f"Fetching answers for '{slug}'...")
    quiz_data = parse_quiz(driver, url)

    if quiz_data["type"] == "image":
        existing = {} if refresh else data.get(slug, {}).get("answers", {})
        merged = {**existing, **quiz_data["answers"]}
        added = len(merged) - len(existing)
        quiz_data["answers"] = merged
        if refresh:
            success("parser", f"Pool reset: {len(merged)} image(s) cached for '{slug}'")
        elif added == 0:
            success("parser", f"No new images found - pool already up to date ({len(merged)} total)")
        else:
            success("parser", f"Added {added} new image(s) to the pool ({len(merged)} total)")
    else:
        success("parser", f"Cached {len(quiz_data['answers'])} answers for '{slug}'")

    data[slug] = quiz_data
    save_answers(config, data)

    if credentials:
        _login_api(driver, config, *credentials)

    return quiz_data