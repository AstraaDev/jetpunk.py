import sys
from datetime import datetime
from colorama import init, Fore, Style

init(autoreset=True)

_LEVEL_STYLES = {
    "INFO": ("", ""),
    "OK": (Fore.GREEN, ""),
    "WARN": (Fore.YELLOW, ""),
    "ERROR": (Fore.RED + Style.BRIGHT, ""),
    "NOTE": (Fore.CYAN, ""),
}

_MODULE_COLOR = {
    "main": Fore.WHITE + Style.BRIGHT,
    "parser": Fore.WHITE + Style.BRIGHT,
    "player": Fore.WHITE + Style.BRIGHT,
    "driver": Fore.WHITE + Style.BRIGHT,
}

def _log(level: str, module: str, msg: str):
    now = datetime.now().strftime("%H:%M:%S")
    fg, _ = _LEVEL_STYLES.get(level, ("", ""))
    mod_color = _MODULE_COLOR.get(module, "")
    dim = Style.DIM

    time_part = f"{dim}{now}{Style.RESET_ALL}"
    level_part = f"{fg}{level:<5}{Style.RESET_ALL}"
    mod_part = f"{mod_color}{module:<7}{Style.RESET_ALL}"
    msg_part = f"{fg}{msg}{Style.RESET_ALL}"

    print(f"  {time_part}  {level_part}  {mod_part}  {msg_part}", file=sys.stderr if level == "ERROR" else sys.stdout)

def info(module: str, msg: str):
    _log("INFO", module, msg)
def success(module: str, msg: str):
    _log("OK", module, msg)
def warning(module: str, msg: str):
    _log("WARN", module, msg)
def error(module: str, msg: str):
    _log("ERROR", module, msg)
def note(module: str, msg: str):
    _log("NOTE", module, msg)