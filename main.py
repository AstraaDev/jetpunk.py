import sys
import argparse

from src.driver import load_config, create_driver, detach_driver, quit_driver
from src.parser import load_answers, fetch_and_cache, quiz_slug, _login_api
from src.player import play_quiz, compute_delays

from src.logger import info, success, warning, error, note

def main():
    parser = argparse.ArgumentParser(description="Automated JetPunk quiz solver using Selenium for DOM extraction and browser control")
    parser.add_argument("--url", help="URL of the JetPunk quiz to play")
    parser.add_argument("--refresh", action="store_true", help="Force re-fetch answers even if already cached")
    parser.add_argument("--list", action="store_true", help="List all cached quizzes")
    parser.add_argument("--login", action="store_true", default=False, help="Log in before starting the quiz")
    parser.add_argument("--time", type=float, metavar="SECONDS", help="Target completion time in seconds (overrides config delays)")
    args = parser.parse_args()

    # Load config first
    try:
        config = load_config()
    except FileNotFoundError:
        error("main", "config.json not found. Copy config.json.example and fill it in")
        sys.exit(1)

    # List cached quizzes
    if args.list:
        data = load_answers(config)
        if not data:
            warning("main", "No cached quizzes yet")
        else:
            print(f"{'Slug':<40} {'Title':<40} {'Answers':>8}")
            print("-" * 92)
            for slug, inf in data.items():
                title = inf.get("title", "?")[:38]
                n = len(inf.get("answers", []))
                print(f"{slug:<40} {title:<40} {n:>8}")
        return

    # Validate URL
    if not args.url:
        parser.print_help()
        sys.exit(1)

    url = args.url.rstrip("/")

    # Build credentials tuple
    credentials = None
    if args.login:
        username = config.get("username", "")
        password = config.get("password", "")
        if not username or not password:
            error("main", "No credentials in config.json (username / password)")
            sys.exit(1)
        credentials = (username, password)

    # Check cache
    cached = load_answers(config)
    slug = quiz_slug(url)
    quiz_data = cached.get(slug)

    driver = create_driver(config)
    completed = False

    try:
        if quiz_data and not args.refresh:
            success("main", f"Found cached answers for '{slug}' ({len(quiz_data['answers'])} answers)")
        else:
            info("main", f"No cache found (or --refresh). Fetching answers for '{slug}'...")
            quiz_data = fetch_and_cache(driver, config, url, credentials)

        if not quiz_data or not quiz_data.get("answers"):
            error("main", "No answers found. The parser may need adjusting for this quiz type")
            sys.exit(1)

        n_answers = len(quiz_data["answers"])
        info("main", f"Playing '{quiz_data.get('title', slug)}' with {n_answers} answers")

        # Recalculate delays if --time is set, otherwise use config values
        if args.time:
            effective_config = compute_delays(config, args.time, quiz_data["answers"])
            if effective_config is None:
                overhead = config["advanced"]["selenium_overhead"]
                min_time = overhead * n_answers
                error("main", f"--time {args.time}s is too short: minimum achievable time for {n_answers} answers is ~{min_time:.0f}s")
                sys.exit(1)
            d = effective_config["delays"]
            note("main", f"--time {args.time}s: delays recalculated (char={d['char_min']:.3f}-{d['char_max']:.3f}s, pause={d['pause_min']:.3f}-{d['pause_max']:.3f}s)")
        else:
            effective_config = config

        note("main", "Press Enter at any time to stop gracefully")

        completed = play_quiz(driver, url, quiz_data["answers"], effective_config, credentials)

    except KeyboardInterrupt:
        warning("main", "Interrupted - stopping...")

    finally:
        if completed:
            # Quiz finished normally: leave the browser open
            detach_driver(driver)
        else:
            # Interrupted or error: close the browser
            quit_driver(driver)

if __name__ == "__main__":
    main()