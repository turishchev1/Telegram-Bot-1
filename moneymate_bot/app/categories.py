"""Default expense categories and the multilingual keyword table used to guess them.

Keywords are matched against words of the user's note. A keyword of 4+ characters matches
any word that starts with it (so "такси" matches "такси", "taxi" matches "taxis");
shorter keywords must match the whole word.
Uzbek keywords are written in Latin script. Apostrophes are ignored on both sides.
"""
from __future__ import annotations

import re

# key, emoji, default bucket
DEFAULT_CATEGORIES = [
    ("food", "🍔", "wants"),
    ("groceries", "🛒", "needs"),
    ("transport", "🚕", "needs"),
    ("bills", "🏠", "needs"),
    ("health", "💊", "needs"),
    ("education", "📚", "needs"),
    ("debt", "💳", "needs"),
    ("shopping", "🛍", "wants"),
    ("fun", "🎮", "wants"),
    ("subscriptions", "📺", "wants"),
    ("gifts", "🎁", "wants"),
    ("savings", "💰", "savings"),
    ("other", "➕", "wants"),
]

KEYWORDS: dict[str, list[str]] = {
    "food": [
        # en
        "coffee", "cafe", "restaurant", "lunch", "dinner", "breakfast", "pizza", "burger",
        "tea", "snack", "takeaway", "fastfood", "sushi", "dessert", "bakery", "food",
        # ru
        "кофе", "кафе", "ресторан", "обед", "ужин", "завтрак", "пицца", "бургер", "чай",
        "перекус", "шаурма", "лагман", "суши", "десерт", "пирожное", "еда",
        # uz
        "qahva", "kafe", "restoran", "tushlik", "kechki", "nonushta", "pitsa", "choy",
        "ovqat", "shashlik", "osh", "lagmon", "somsa", "shirinlik", "kofe",
    ],
    "groceries": [
        "groceries", "grocery", "supermarket", "market", "bread", "milk", "vegetables",
        "fruits", "fruit", "meat", "eggs",
        "продукты", "магазин", "супермаркет", "рынок", "базар", "хлеб", "молоко", "овощи",
        "фрукты", "мясо", "яйца",
        "bozor", "dokon", "supermarket", "non", "sut", "sabzavot", "meva", "gosht",
        "oziqovqat", "mahsulot", "mahsulotlar", "tuxum",
    ],
    "transport": [
        "taxi", "uber", "bus", "metro", "fuel", "petrol", "gasoline", "parking", "train",
        "flight", "ticket", "yandex", "indrive", "mytaxi", "propane", "methane", "transport",
        "такси", "автобус", "метро", "бензин", "топливо", "парковка", "проезд", "билет",
        "поезд", "самолет", "яндекс", "индрайв", "пропан", "метан", "транспорт",
        "taksi", "avtobus", "benzin", "yoqilgi", "parkovka", "bilet", "poyezd", "samolyot",
        "propan", "metan", "yol", "transport",
    ],
    "bills": [
        "rent", "electricity", "water", "utilities", "internet", "wifi", "phone", "mobile",
        "bills", "bill", "heating",
        "аренда", "квартплата", "коммуналка", "коммунальные", "электричество", "свет",
        "вода", "газ", "интернет", "телефон", "связь", "отопление",
        "ijara", "kommunal", "elektr", "svet", "suv", "gaz", "aloqa", "hisob", "isitish",
    ],
    "health": [
        "pharmacy", "medicine", "doctor", "dentist", "hospital", "vitamins", "clinic",
        "gym", "fitness", "sport", "health", "tests",
        "аптека", "лекарство", "лекарства", "врач", "стоматолог", "больница", "витамины",
        "клиника", "анализы", "спортзал", "фитнес", "спорт",
        "dori", "dorixona", "shifokor", "doktor", "tish", "kasalxona", "vitamin", "klinika",
        "tahlil", "sport", "fitnes",
    ],
    "education": [
        "course", "courses", "tuition", "school", "university", "book", "books", "exam",
        "lesson", "tutor", "education", "study",
        "курс", "курсы", "учеба", "обучение", "школа", "университет", "книга", "книги",
        "репетитор", "экзамен", "урок", "контракт",
        "kurs", "oqish", "maktab", "universitet", "kitob", "repetitor", "imtihon", "dars",
        "kontrakt", "talim",
    ],
    "debt": [
        "debt", "loan", "credit", "installment", "mortgage", "repayment",
        "долг", "кредит", "рассрочка", "ипотека", "займ", "заем",
        "qarz", "kredit", "nasiya", "ipoteka", "rassrochka",
    ],
    "shopping": [
        "clothes", "shoes", "shopping", "mall", "clothing", "cosmetics", "gadget",
        "electronics", "sneakers", "jacket", "bag",
        "одежда", "обувь", "шопинг", "торговый", "косметика", "техника", "вещи", "кроссовки",
        "куртка", "сумка",
        "kiyim", "poyabzal", "kosmetika", "texnika", "krossovka", "kurtka", "sumka",
    ],
    "fun": [
        "cinema", "movie", "game", "games", "concert", "bar", "club", "party", "hobby", "fun",
        "bowling", "entertainment",
        "кино", "игра", "игры", "концерт", "бар", "клуб", "вечеринка", "хобби", "развлечения",
        "боулинг",
        "kino", "oyin", "oyinlar", "konsert", "klub", "bazm", "hobbi", "bowling",
    ],
    "subscriptions": [
        "subscription", "netflix", "spotify", "youtube", "premium", "icloud", "chatgpt",
        "подписка", "нетфликс", "спотифай", "премиум", "ютуб",
        "obuna", "premium",
    ],
    "gifts": [
        "gift", "present", "birthday", "wedding", "donation", "charity",
        "подарок", "подарки", "свадьба", "благотворительность", "садака", "рождения",
        "sovga", "tuhfa", "toy", "tugilgan", "sadaqa", "xayriya",
    ],
    "savings": [
        "savings", "saving", "deposit", "invest", "investment", "emergency",
        "накопления", "сбережения", "депозит", "инвестиции", "копилка", "отложил",
        "jamgarma", "omonat", "depozit", "investitsiya", "tejash",
    ],
}

INCOME_WORDS = [
    "salary", "income", "paycheck", "paycheque", "wage", "bonus", "stipend", "scholarship",
    "зарплата", "зарплату", "доход", "аванс", "премия", "стипендия",
    "maosh", "oylik", "daromad", "stipendiya", "avans",
]

_APOSTROPHES = "'ʻʼ’‘`´"
_WORD_RE = re.compile(r"[\w]+", re.UNICODE)


def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    for ch in _APOSTROPHES:
        text = text.replace(ch, "")
    return text


def tokens(text: str) -> list[str]:
    return _WORD_RE.findall(normalize(text))


def _kw_matches(token: str, keyword: str) -> bool:
    if token == keyword:
        return True
    return len(keyword) >= 4 and token.startswith(keyword)


def guess_default_category(note: str) -> str | None:
    """Return the key of the default category the note most likely belongs to."""
    toks = tokens(note)
    if not toks:
        return None
    # earlier words in the note win; within a word, table order wins
    for tok in toks:
        for key, words in KEYWORDS.items():
            for kw in words:
                if _kw_matches(tok, normalize(kw)):
                    return key
    return None


def is_income_word(token: str) -> bool:
    return any(_kw_matches(token, normalize(w)) for w in INCOME_WORDS)


def match_custom(note: str, custom: list[tuple[int, str]]) -> int | None:
    """custom: list of (category_id, name). Returns the id whose name appears in the note."""
    toks = tokens(note)
    for cid, name in custom:
        name_toks = tokens(name)
        if name_toks and all(any(_kw_matches(t, nt) or t == nt for t in toks) for nt in name_toks):
            return cid
    return None
