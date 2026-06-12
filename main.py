import sys
import argparse

from src.driver import load_config, create_driver
from src.parser import load_answers, fetch_and_cache, quiz_slug
from src.player import play_quiz

def main():
    parser = argparse.ArgumentParser(description="Automated JetPunk quiz solver using Selenium for DOM extraction and browser control")
    parser.add_argument("url", nargs="?", help="URL of the JetPunk quiz to play")
    parser.add_argument("--refresh", action="store_true", help="Force re-fetch answers even if already cached")
    parser.add_argument("--list", action="store_true", help="List all cached quizzes")
    args = parser.parse_args()

    # List cached quizzes
    if args.list:
        data = load_answers()
        if not data:
            print("No cached quizzes yet")
        else:
            print(f"{'Slug':<40} {'Title':<40} {'Answers':>8}")
            print("-" * 92)
            for slug, info in data.items():
                title = info.get("title", "?")[:38]
                n = len(info.get("answers", []))
                print(f"{slug:<40} {title:<40} {n:>8}")
        return

    # Validate URL
    if not args.url:
        parser.print_help()
        sys.exit(1)

    url = args.url.rstrip("/")

    # Load config
    try:
        config = load_config()
    except FileNotFoundError:
        print("ERROR: config.json not found. Copy config.json.example and fill it in")
        sys.exit(1)

    # Check cache
    cached = load_answers()
    slug = quiz_slug(url)
    quiz_data = cached.get(slug)

    if quiz_data and not args.refresh:
        print(f"[main] Found cached answers for '{slug}' ({len(quiz_data['answers'])} answers)")
    else:
        # Need to fetch, launch browser
        print(f"[main] No cache found (or --refresh). Fetching answers for '{slug}'...")
        driver = create_driver(config)
        try:
            quiz_data = fetch_and_cache(driver, url)
        finally:
            driver.quit()

    if not quiz_data or not quiz_data.get("answers"):
        print("[main] ERROR: No answers found. The parser may need adjusting for this quiz type")
        sys.exit(1)

    # Play the quiz
    print(f"\n[main] Playing '{quiz_data.get('title', slug)}' with {len(quiz_data['answers'])} answers")
    driver = create_driver(config)
    try:
        play_quiz(driver, url, quiz_data["answers"], config)
        input("\n[main] Press Enter to close the browser...")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
