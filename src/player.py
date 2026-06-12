import time
import random
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from src.parser import _start_quiz, _find_input, accept_cookies

# Navigate to the quiz, start it, and type all answers
def play_quiz(driver: webdriver.Chrome, url: str, answers: list[str], config: dict):
    delay_min = config.get("delay_min")
    delay_max = config.get("delay_max")
    wait = WebDriverWait(driver, 15)

    print(f"[player] Loading quiz: {url}")
    driver.get(url)
    accept_cookies(driver, wait)

    # Start the quiz
    _start_quiz(driver, wait)
    print("[player] Quiz started")

    # Locate the answer input
    input_box = _find_input(driver, wait)

    print(f"[player] Input found. Typing {len(answers)} answers...")
    submitted = 0

    for answer in answers:
        try:
            # Click the input first to make sure it's focused
            input_box.click()
            input_box.clear()
            _type_answer(input_box, answer, delay_min, delay_max)
            input_box.send_keys(Keys.RETURN)
            submitted += 1

            time.sleep(random.uniform(delay_min, delay_max))

        except Exception as e:
            print(f"[player] Warning on '{answer}': {e}")
            input_box = _find_input(driver, wait)
            if input_box is None:
                print("[player] Lost the input box, stopping")
                break

    print(f"[player] Done - submitted {submitted}/{len(answers)} answers")

# Type answer character by character with slight randomness
def _type_answer(input_box, text: str, delay_min: float, delay_max: float):
    for char in text:
        input_box.send_keys(char)
        time.sleep(random.uniform(delay_min / 4, delay_max / 4))
