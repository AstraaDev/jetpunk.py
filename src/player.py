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
from src.logger import info, success, warning, error

# Normalise text
def _normalize(text: str) -> str:
    return text.lower().replace("-", " ")

# DOM helpers
def _get_num_guessed(driver: webdriver.Chrome) -> int:
    try:
        return int(driver.find_element(By.ID, "num-guessed").text.strip())
    except Exception:
        return 0

# Check if the quiz is still active (timer not expired, not 100%)
def _quiz_still_active(driver: webdriver.Chrome) -> bool:
    try:
        box = driver.find_element(By.ID, "txt-answer-box")
        return box.is_enabled() and box.is_displayed()
    except Exception:
        return False

# Recalculate delays to fit a target completion time :
#   Each answer carries an unavoidable Selenium overhead (config advanced.selenium_overhead)
#   compute_delays subtracts this overhead first, then distributes the
#   remaining budget between per-char sleeps (60%) and inter-answer pauses (40%)
def compute_delays(config: dict, target_seconds: float, answers: list[str]) -> dict | None:
    overhead = config["advanced"]["selenium_overhead"]
    n_answers = len(answers)
    avg_chars = sum(len(_normalize(a)) for a in answers) / n_answers

    min_achievable = overhead * n_answers
    if target_seconds <= min_achievable:
        return None

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
def _finish(bar, guessed: int, total: int) -> tuple[int, bool]:
    final = total if guessed >= total - 1 else guessed
    bar.n = final
    return final, True

# Main play function
def play_quiz(driver: webdriver.Chrome, url: str, answers: list[str], config: dict, credentials: tuple[str, str] | None = None) -> bool:
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

    _start_quiz(driver, wait)
    success("player", "Quiz started")

    input_box = _find_input(driver, wait)
    total = len(answers)
    info("player", f"Input found. Typing {total} answers...")

    guessed = _get_num_guessed(driver)
    completed = False
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
                guessed, completed = _finish(bar, guessed, total)
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
                guessed, completed = _finish(bar, guessed, total)
                break
            except Exception as e:
                warning("player", f"Warning on '{answer}': {e}")
                input_box = _find_input(driver, wait)
                if input_box is None:
                    warning("player", "Lost the input box, stopping")
                    break

        # All answers iterated without the loop breaking
        else:
            guessed, completed = _finish(bar, guessed, total)

    success("player", f"Done - {guessed}/{total} answers validated")

    return completed

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