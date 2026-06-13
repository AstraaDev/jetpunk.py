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
    "selenium_overhead": 0.36,
    "login_api": "https://www.jetpunk.com/api/login.php",
    "login_referer": "https://www.jetpunk.com/user/login?language=english"
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

| Option           | Description                                                              |
| ---------------- | ------------------------------------------------------------------------ |
| `--url URL`      | Quiz URL (required for all operations except `--list`)                   |
| `--scrape`       | Scrape and cache answers for the quiz, then exit (requires `--url`)      |
| `--refresh`      | Reset the cached answer pool instead of merging (requires `--scrape`)    |
| `--list`         | List all cached quizzes                                                  |
| `--login`        | Log in before launching the quiz (requires `--url`)                      |
| `--shuffle`      | Randomize answer order before typing (requires `--url`)                  |
| `--time SECONDS` | Target completion time in seconds (requires `--url`)                     |

---

## Workflow

Answers must be scraped and cached before playing. For standard quizzes a single
`--scrape` run is enough. For quizzes that show a random subset of questions each
time (e.g. flag quizzes), run `--scrape` several times to accumulate the full pool.

```
--scrape          Fetch answers → merge into cache → exit
--scrape --refresh  Reset cache, fetch fresh answers → exit
--url             Play using the cached answers (error if none found)
```

---

## Examples

### Scrape a standard quiz

```bash
python main.py --url https://www.jetpunk.com/quizzes/how-many-countries-can-you-name --scrape
```

### Accumulate answers for a random-subset quiz (run multiple times)

```bash
python main.py --url https://www.jetpunk.com/user-quizzes/176412/pays-aleatoire-par-drapeau --scrape
python main.py --url https://www.jetpunk.com/user-quizzes/176412/pays-aleatoire-par-drapeau --scrape
# repeat until the pool is complete enough
```

### Play a quiz

```bash
python main.py --url https://www.jetpunk.com/quizzes/how-many-countries-can-you-name
```

### Play with a shuffled order and a target time of 4 minutes

```bash
python main.py --url https://www.jetpunk.com/quizzes/how-many-countries-can-you-name --shuffle --time 240
```

### Log in and play

```bash
python main.py --url https://www.jetpunk.com/quizzes/how-many-countries-can-you-name --login
```

### Reset the cache for a quiz and re-scrape

```bash
python main.py --url https://www.jetpunk.com/quizzes/how-many-countries-can-you-name --scrape --refresh
```

### List cached quizzes

```bash
python main.py --list
```