import sys
import time
import random
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import ElementNotInteractableException, StaleElementReferenceException
from tqdm import tqdm

from src.parser import _start_quiz, _find_input, accept_cookies, _login_api, _wait_for_cloudflare
from src.logger import info, success, warning, error, format_log

# Normalise text
def _normalize(text: str) -> str:
    return text.lower().replace("-", " ").replace("\n", " ")

# DOM helpers
def _get_num_guessed(driver: webdriver.Chrome) -> int:
    try:
        return int(driver.find_element(By.ID, "num-guessed").text.strip())
    except Exception:
        return 0

# Check if the quiz is still active (timer not expired, not 100%)
def _quiz_still_active(driver: webdriver.Chrome, quiz_type: str = "text") -> bool:
    try:
        if quiz_type == "map":
            return int(driver.find_element(By.ID, "num-remaining").text.strip()) > 0
        if quiz_type == "sudden_death":
            return int(driver.find_element(By.ID, "num-remaining").text.strip()) > 0
        box = driver.find_element(By.ID, "txt-answer-box")
        return box.is_enabled() and box.is_displayed()
    except Exception:
        return False

# Find the image src corresponding to the currently highlighted answer slot
def _get_current_image_src(driver: webdriver.Chrome) -> str | None:
    try:
        highlighted = driver.find_element(By.CSS_SELECTOR, "div.answer-display.highlighted")
    except Exception:
        return None

    answer_class = highlighted.get_attribute("class")
    target_id = next((c.replace("answer-", "") for c in answer_class.split() if c.startswith("answer-") and c not in ("answer-display", "answer-holder")), None)
    if not target_id:
        return None

    try:
        photo = driver.find_element(By.CSS_SELECTOR, f"div.photo-holder.scroll-target-{target_id} img")
        return photo.get_attribute("src")
    except Exception:
        return None

# Move the highlight to the next answer slot
def _skip_current_image(driver: webdriver.Chrome) -> bool:
    try:
        highlighted = driver.find_element(By.CSS_SELECTOR, "div.answer-display.highlighted")
        all_slots = driver.find_elements(By.CSS_SELECTOR, "div.answer-display")
        index = all_slots.index(highlighted)
        if index + 1 >= len(all_slots):
            return False

        target = all_slots[index + 1]
        for attempt in range(5):
            try:
                target.click()
                return True
            except Exception:
                time.sleep(0.2)
        return False
    except Exception:
        pass
    return False

# Recalculate delays to fit a target completion time :
#   Each answer carries an unavoidable Selenium overhead (config advanced.selenium_overhead)
#   compute_delays subtracts this overhead first, then distributes the
#   remaining budget between per-char sleeps (60%) and inter-answer pauses (40%)
def compute_delays(config: dict, target_seconds: float, answers: list[str], quiz_type: str = "text") -> dict | None:
    overhead = config["advanced"]["selenium_overhead"]
    n_answers = len(answers)

    min_achievable = overhead * n_answers
    if target_seconds <= min_achievable:
        return None

    # Map quizzes have no typing, distribute all budget to pauses only
    if quiz_type == "map":
        pause_budget = (target_seconds / n_answers) - overhead
        pause_min = max(0.010, pause_budget * 0.5)
        pause_max = max(pause_min, pause_budget * 1.5)
        return {**config, "delays": {**config["delays"], "pause_min": pause_min, "pause_max": pause_max}}

    avg_chars = sum(len(_normalize(a)) for a in answers) / n_answers
    time_per_answer = target_seconds / n_answers
    controllable = time_per_answer - overhead

    char_budget = controllable * 0.60
    pause_budget = controllable * 0.40

    sleep_per_char = char_budget / avg_chars
    char_spread = sleep_per_char * 0.4
    char_min = max(0.001, sleep_per_char - char_spread)
    char_max = sleep_per_char + char_spread

    pause_min = max(0.010, pause_budget * 0.5)
    pause_max = max(pause_min, pause_budget * 1.5)

    return {**config, "delays": {**config["delays"], "char_min": char_min, "char_max": char_max, "pause_min": pause_min, "pause_max": pause_max}}

# Waits for Enter key in a background thread, then sets the stop event
def _watch_for_enter(stop_event: threading.Event):
    try:
        sys.stdin.readline()
    except Exception:
        pass
    stop_event.set()

# Snap the bar to the right count on completion
def _finish(bar, guessed: int, total: int) -> int:
    final = total if guessed >= total - 1 else guessed
    bar.n = final
    return final

# Main play function
def play_quiz(driver: webdriver.Chrome, url: str, answers: list[str], config: dict, credentials: tuple[str, str] | None = None, quiz_type: str = "text") -> bool:
    delays = config["delays"]
    char_min = delays["char_min"]
    char_max = delays["char_max"]
    pause_min = delays["pause_min"]
    pause_max = delays["pause_max"]
    wait = WebDriverWait(driver, 15)

    info("player", f"Loading quiz: {url}")
    driver.get(url)
    _wait_for_cloudflare(driver)
    accept_cookies(driver, wait)

    if credentials:
        already_logged_in = any(c["name"] == "jpUserHash" for c in driver.get_cookies())
        if not already_logged_in:
            _login_api(driver, config, *credentials)

    accept_cookies(driver, wait)
    _start_quiz(driver, wait)
    success("player", "Quiz started")

    if quiz_type == "map":
        return _play_map_quiz(driver, answers, pause_min, pause_max)

    if quiz_type == "sudden_death":
        return _play_sudden_death_quiz(driver, answers, pause_min, pause_max)

    input_box = _find_input(driver, wait)
    total = len(answers)
    info("player", f"Input found. Typing {total} answers...")

    if quiz_type == "image":
        return _play_image_quiz(driver, input_box, answers, char_min, char_max, pause_min, pause_max)

    return _play_text_quiz(driver, wait, input_box, answers, char_min, char_max, pause_min, pause_max)

# Play a text-style quiz
def _play_text_quiz(driver: webdriver.Chrome, wait: WebDriverWait, input_box, answers: list[str], char_min: float, char_max: float, pause_min: float, pause_max: float) -> bool:
    total = len(answers)
    guessed = _get_num_guessed(driver)
    stop_event = threading.Event()
    watcher = threading.Thread(target=_watch_for_enter, args=(stop_event,), daemon=True)
    watcher.start()

    with tqdm(total=total, initial=guessed, unit="ans", dynamic_ncols=True, leave=True) as bar:
        for answer in answers:
            if stop_event.is_set():
                bar.leave = False
                break
            # Stop cleanly if the quiz ended (timer expired or all answers found)
            if not _quiz_still_active(driver):
                guessed = _finish(bar, guessed, total)
                break
            try:
                input_box.click()
                input_box.clear()

                validated = _type_until_validated(driver, input_box, answer, char_min, char_max, guessed, stop_event)

                if stop_event.is_set():
                    bar.leave = False
                    break

                if validated:
                    guessed += 1
                    bar.update(1)
                else:
                    input_box.send_keys(Keys.RETURN)
                    time.sleep(0.2)
                    new_guessed = _get_num_guessed(driver)
                    if new_guessed > guessed:
                        bar.update(new_guessed - guessed)
                        guessed = new_guessed

                time.sleep(random.uniform(pause_min, pause_max))

            except (ElementNotInteractableException, StaleElementReferenceException):
                guessed = _finish(bar, guessed, total)
                break
            except Exception as e:
                bar.write(format_log("WARN", "player", f"Warning on '{answer}': {e}"))
                input_box = _find_input(driver, wait)
                if input_box is None:
                    bar.write(format_log("WARN", "player", "Lost the input box, stopping"))
                    break

        # All answers iterated without the loop breaking
        else:
            guessed = _finish(bar, guessed, total)

    success("player", f"Done - {guessed}/{total} answers validated")

    return True

# Play a map-style quiz
def _play_map_quiz(driver: webdriver.Chrome, answers: dict, pause_min: float, pause_max: float) -> bool:
    total = len(answers)
    guessed = 0
    stop_event = threading.Event()
    watcher = threading.Thread(target=_watch_for_enter, args=(stop_event,), daemon=True)
    watcher.start()

    with tqdm(total=total, unit="ans", dynamic_ncols=True, leave=True) as bar:
        for _ in range(total):
            if stop_event.is_set():
                bar.leave = False
                break
            if not _quiz_still_active(driver, quiz_type="map"):
                guessed = _finish(bar, guessed, total)
                break
            try:
                # Find the highlighted country on the SVG map
                path = driver.find_element(By.CSS_SELECTOR, "path.map-highlight")
                country_id = path.get_attribute("id")

                # Look up the label from cache
                label = answers.get(country_id)
                if label is None:
                    bar.write(format_log("WARN", "player", f"No cached answer for country id '{country_id}', skipping"))
                    driver.find_element(By.CSS_SELECTOR, "button.map-highlight-next").click()
                    bar.update(1)
                    time.sleep(random.uniform(pause_min, pause_max))
                    continue

                # Find the matching answer div by label text and click it
                answer_div = next((d for d in driver.find_elements(By.CSS_SELECTOR, "div.map-answer") if d.text.strip().replace("\n", " ") == label), None)
                if answer_div is None:
                    bar.write(format_log("WARN", "player", f"Answer div not found for '{label}', skipping"))
                    driver.find_element(By.CSS_SELECTOR, "button.map-highlight-next").click()
                    bar.update(1)
                    time.sleep(random.uniform(pause_min, pause_max))
                    continue

                answer_div.click()
                guessed += 1
                bar.update(1)
                time.sleep(random.uniform(pause_min, pause_max))
            except (ElementNotInteractableException, StaleElementReferenceException):
                guessed = _finish(bar, guessed, total)
                break
            except Exception as e:
                bar.write(format_log("WARN", "player", f"Warning while solving map quiz: {e}"))
                break
        else:
            guessed = _finish(bar, guessed, total)

    success("player", f"Done - {guessed}/{total} answers validated")
    return True

# Play an image-style quiz
def _play_image_quiz(driver: webdriver.Chrome, input_box, answers: dict, char_min: float, char_max: float, pause_min: float, pause_max: float) -> bool:
    # Use the number of slots actually present on the page
    total = len(driver.find_elements(By.CSS_SELECTOR, "div.answer-display"))
    guessed = 0
    skipped = 0
    warned_images = set()
    stop_event = threading.Event()
    watcher = threading.Thread(target=_watch_for_enter, args=(stop_event,), daemon=True)
    watcher.start()

    with tqdm(total=total, unit="ans", dynamic_ncols=True, leave=True) as bar:
        for _ in range(total):
            if stop_event.is_set():
                bar.leave = False
                break
            if not _quiz_still_active(driver):
                guessed = _finish(bar, guessed, total)
                break
            try:
                img_src = _get_current_image_src(driver)
                answer = answers.get(img_src)
                if answer is None:
                    if img_src not in warned_images:
                        bar.write(format_log("WARN", "player", f"No cached answer for image '{img_src}', skipping"))
                        warned_images.add(img_src)
                    skipped += 1
                    if not _skip_current_image(driver):
                        break
                    bar.update(1)
                    continue

                for char in _normalize(answer):
                    if stop_event.is_set():
                        break
                    input_box.send_keys(char)
                    time.sleep(random.uniform(char_min, char_max))

                if stop_event.is_set():
                    bar.leave = False
                    break

                input_box.send_keys(Keys.RETURN)
                guessed += 1
                bar.update(1)

                time.sleep(random.uniform(pause_min, pause_max))

            except (ElementNotInteractableException, StaleElementReferenceException):
                guessed = _finish(bar, guessed, total)
                break
            except Exception as e:
                bar.write(format_log("WARN", "player", f"Warning while solving image quiz: {e}"))
                break

        # All answers iterated without the loop breaking
        else:
            guessed = _finish(bar, guessed, total)

    success("player", f"Done - {guessed}/{total} answers validated")

    return True

# Play a sudden death quiz
def _play_sudden_death_quiz(driver: webdriver.Chrome, answers: list[str], pause_min: float, pause_max: float) -> bool:
    correct_ids = set(answers)
    total = len(correct_ids)
    guessed = 0
    stop_event = threading.Event()
    watcher = threading.Thread(target=_watch_for_enter, args=(stop_event,), daemon=True)
    watcher.start()

    with tqdm(total=total, unit="ans", dynamic_ncols=True, leave=True) as bar:
        items = driver.find_elements(By.CSS_SELECTOR, "div.grid-item.active")
        for item in items:
            if stop_event.is_set():
                bar.leave = False
                break
            if not _quiz_still_active(driver, quiz_type="sudden_death"):
                guessed = _finish(bar, guessed, total)
                break
            try:
                data_id = item.get_attribute("data-id")
                if data_id not in correct_ids:
                    continue
                item.click()
                guessed += 1
                bar.update(1)
                time.sleep(random.uniform(pause_min, pause_max))

            except (ElementNotInteractableException, StaleElementReferenceException):
                guessed = _finish(bar, guessed, total)
                break
            except Exception as e:
                bar.write(format_log("WARN", "player", f"Warning while solving sudden death quiz: {e}"))
                break

        else:
            guessed = _finish(bar, guessed, total)

    success("player", f"Done - {guessed}/{total} answers validated")
    return True

# Typing simulation with random delays, interruptible via stop_event
def _type_until_validated(driver: webdriver.Chrome, input_box, text: str, char_min: float, char_max: float, guessed_before: int, stop_event: threading.Event) -> bool:
    for char in _normalize(text):
        if stop_event.is_set():
            return False
        input_box.send_keys(char)
        time.sleep(random.uniform(char_min, char_max))

        if _get_num_guessed(driver) > guessed_before:
            input_box.send_keys(Keys.RETURN)
            return True

    return False