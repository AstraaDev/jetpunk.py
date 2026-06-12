import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm

from src.parser import _start_quiz, _find_input, accept_cookies
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

# Main play function
def play_quiz(driver: webdriver.Chrome, url: str, answers: list[str], config: dict):
    delay_min = config.get("delay_min")
    delay_max = config.get("delay_max")
    pause_min = config.get("pause_min")
    pause_max = config.get("pause_max")
    wait = WebDriverWait(driver, 15)

    info("player", f"Loading quiz: {url}")
    driver.get(url)
    accept_cookies(driver, wait)

    _start_quiz(driver, wait)
    success("player", "Quiz started")

    input_box = _find_input(driver, wait)
    total = len(answers)
    info("player", f"Input found. Typing {total} answers...")

    guessed = _get_num_guessed(driver)

    with tqdm(total=total, initial=guessed, unit="ans", dynamic_ncols=True) as bar:
        for answer in answers:
            try:
                input_box.click()
                input_box.clear()

                validated = _type_until_validated(driver, input_box, answer, delay_min, delay_max, guessed)

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

            except Exception as e:
                warning("player", f"Warning on '{answer}': {e}")
                input_box = _find_input(driver, wait)
                if input_box is None:
                    warning("player", "Lost the input box, stopping")
                    break

    success("player", f"Done - {guessed}/{total} answers validated")

# Typing simulation with random delays
def _type_until_validated(driver: webdriver.Chrome, input_box, text: str, delay_min: float, delay_max: float, guessed_before: int) -> bool:
    for char in _normalize(text):
        input_box.send_keys(char)
        time.sleep(random.uniform(delay_min / 4, delay_max / 4))

        if _get_num_guessed(driver) > guessed_before:
            input_box.send_keys(Keys.RETURN)
            return True

    return False