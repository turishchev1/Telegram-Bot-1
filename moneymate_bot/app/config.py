"""Settings, read from environment variables or a .env file next to bot.py."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
DB_PATH: Path = Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "moneymate.db")))
DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "Asia/Tashkent")
DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "en")
DEFAULT_CURRENCY: str = os.getenv("DEFAULT_CURRENCY", "UZS")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}

LANGUAGES = {"en": "English", "ru": "Русский", "uz": "O'zbekcha"}
CURRENCIES = ["UZS", "USD", "RUB", "EUR"]
BUCKETS = ["needs", "wants", "savings"]
SPLIT_TEMPLATES = {
    "50_30_20": (50, 30, 20),
    "70_20_10": (70, 20, 10),
    "80_10_10": (80, 10, 10),
    "60_30_10": (60, 30, 10),
}
DEFAULT_SPLIT = (50, 30, 20)
BANNER_PATH = BASE_DIR / "assets" / "banner.png"
PAGE_SIZE = 10
