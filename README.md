# jetpunk.py

Automated JetPunk quiz solver built with Selenium for browser automation and DOM interaction.

## Requirements

* Python 3.10+
* Google Chrome

Install dependencies:

```bash
pip install selenium requests tqdm colorama
```

> ChromeDriver is managed automatically by Selenium Manager. No manual installation is required.

---

## Configuration

Configure `config.json`:

```json
{
  "chrome_path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "username": "",
  "password": "",
  "delays": {
    "char_min": 0.03,
    "char_max": 0.37,
    "pause_min": 0.2,
    "pause_max": 1.2
  },
  "advanced": {
    "answers_file": "answers.json",
    "selenium_overhead": 0.36
  }
}
```

### Configuration Reference

| Field                        | Description                                        |
| ---------------------------- | -------------------------------------------------- |
| `chrome_path`                | Path to the Chrome executable                      |
| `username` / `password`      | JetPunk credentials (required only with `--login`) |
| `delays.char_min/max`        | Random delay between keystrokes (seconds)          |
| `delays.pause_min/max`       | Random delay between submitted answers (seconds)   |
| `advanced.answers_file`      | Local answer cache file                            |
| `advanced.selenium_overhead` | Estimated Selenium overhead used by `--time`       |

---

## Usage

```bash
python main.py [OPTIONS]
```

### Options

| Option           | Description                            |
| ---------------- | -------------------------------------- |
| `--url URL`      | Quiz URL                               |
| `--refresh`      | Refresh cached answers before starting |
| `--list`         | List cached quizzes                    |
| `--login`        | Log in before launching the quiz       |
| `--shuffle`      | Randomize answer order                 |
| `--time SECONDS` | Target completion time                 |

---

## Examples

### Play a quiz

```bash
python main.py --url https://www.jetpunk.com/quizzes/how-many-countries-can-you-name
```

### Refresh answers and play

```bash
python main.py --url https://www.jetpunk.com/quizzes/how-many-countries-can-you-name --refresh
```

### Log in and simulate a 4-minute completion

```bash
python main.py --url https://www.jetpunk.com/quizzes/how-many-countries-can-you-name --login --time 240 --shuffle
```

### List cached quizzes

```bash
python main.py --list
```
