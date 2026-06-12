import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from src.logger import success, error

def load_config(path="config.json") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _build_options(config: dict) -> Options:
    options = Options()
    if config.get("chrome_path"):
        options.binary_location = config["chrome_path"]
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options

def _patch_webdriver(driver: webdriver.Chrome) -> webdriver.Chrome:
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def create_driver(config: dict) -> webdriver.Chrome:
    options = _build_options(config)
    try:
        driver = webdriver.Chrome(options=options)
        success("driver", f"ChromeDriver auto-resolved: {driver.service.path}")
        return _patch_webdriver(driver)
    except Exception as e:
        error("driver", f"Selenium Manager failed: {e}")
        return None