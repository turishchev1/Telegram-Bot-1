# MoneyMate: Telegram expense and budget bot

A Telegram bot that tracks your spending, splits every paycheck into budget buckets,
shows your spending habits (for example which month you spend the most in), sends a daily
money tip and a monthly Excel report. Works in **English, Русский and O'zbekcha (Latin)**.

## What it does

| Area | Features |
|---|---|
| **Adding expenses** | One-line entry: `coffee 15000`, `taxi 22k yesterday`, `такси 30 тыс 12.11`. Send **only a number** (`15000`) and the bot asks for category, date and an optional note. Categories are recognised in all three languages (`taxi` / `такси` / `taksi`). `/undo`, change category, delete. |
| **Income splitting** | `+1000000 salary` (or `/income`): the bot asks how to split it, with templates (50/30/20, 70/20/10, 80/10/10, 60/30/10), your saved usual split, or a custom split like `80 10 10`. Money goes into **Needs / Wants / Savings** buckets. |
| **Balances** | `/balance` shows what is left in each bucket. Warnings when a bucket is nearly empty or over budget. Unspent money rolls over. |
| **Looking things up** | `/today` `/week` `/month`, `/show transport`, `/show food last month`, `/show food october`, `/show wants week`, `/show food over 50000`, `/search uber`, `/top`, `/top categories`, `/categories` menu. Paged lists, tap a number to edit or delete an entry, export any list as CSV. |
| **Habit insights** | `/stats`: highest and lowest month, priciest weekday, biggest category, categories that grew, no-spend days, needs/wants/savings mix. `/chart`: charts by month, category and weekday. |
| **Excel report** | `/export` (also `/export last month`, `/export 2026`, `/export all`). The bot also sends last month's report **automatically in the first week of each month**. |
| **Daily tips** | 40 tips in each language, one per day at the time you choose (`/tiptime 09:00`), never repeated until all are used, leaning towards debt, student or saving tips when they fit you. `/tips on` `/tips off` `/tip`. |
| **Onboarding** | Welcome banner, language, currency, then name, age, job, income, debts and goal. Every question can be skipped, answers are remembered (`/profile`). |
| **Settings** | Language, currency, time zone, usual split, tips on/off, guided entry on/off, evening reminders, custom categories (`/newcategory Pets 🐶`). |
| **Privacy** | `/deletedata` permanently erases everything about the user. |
| **Owner** | `/admin` (only for IDs in `ADMIN_IDS`): number of users, active users, entries. |

### What is not included (yet)

Voice input, receipt photo scanning, bank SMS parsing, a Telegram Mini App dashboard,
shared/group expenses, recurring expenses that log themselves, fixed amounts taken off the top
of an income before splitting, per-entry currencies and savings goals. The architecture
leaves room for all of them.

### A note on "Saved Messages"

Telegram does not let bots write into a person's **Saved Messages**. The bot sends the monthly
report to the chat with the bot (which already works as a permanent archive) and tells the user
they can forward it to Saved Messages with two taps.

---

## 1. Set the bot up (about 10 minutes)

### Step 1: create the bot on Telegram

1. Open Telegram and talk to **@BotFather** (the official bot for making bots).
2. Send `/newbot`.
3. Choose a display name (for example `MoneyMate`) and a username that ends in `bot`
   (for example `my_moneymate_bot`).
4. BotFather replies with a **token** that looks like `123456789:AAH...`. Copy it. Treat it like a password.
5. Optional but nice: send `/setuserpic` and upload `assets/logo.png`; `/setdescription` and
   `/setabouttext` to describe the bot.

Telegram does not host your code. The bot "lives" wherever you run `python bot.py`; the token
is what connects that program to your bot's name on Telegram.

### Step 2: install Python and the bot

You need **Python 3.10 or newer**.

**Windows** (if you saw *"Python was not found; run without arguments to install from the Microsoft Store"*, this is for you):

1. Download Python from <https://www.python.org/downloads/> and run the installer.
   **Tick "Add python.exe to PATH" on the first screen**, then click Install.
2. Close and reopen the terminal (Command Prompt or PowerShell). Check with `py --version`.
   If `python` still opens the Microsoft Store, turn the shortcut off in
   *Settings > Apps > Advanced app settings > App execution aliases* (switch off the two "python" entries),
   or just use `py` instead of `python` everywhere below.
3. Right-click the zip, choose **Extract All**, then open a terminal in the extracted `moneymate_bot` folder
   (in File Explorer click the address bar, type `cmd`, press Enter) and run:

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

If PowerShell refuses to run `activate`, use Command Prompt (cmd) instead, or run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

**macOS / Linux:**

```bash
unzip moneymate_bot.zip
cd moneymate_bot

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### Step 3: add your token

```bash
cp .env.example .env                 # Windows (cmd): copy .env.example .env
```

Open `.env` in any text editor (Windows: `notepad .env`) and replace the placeholder after `BOT_TOKEN=` with your real token.
Optionally set `ADMIN_IDS` (your numeric Telegram ID, from @userinfobot) and the defaults for
language, currency and time zone.

### Step 4: run it

```bash
python bot.py                        # Windows: py bot.py  (or just python bot.py inside the activated .venv)
```

You should see `Bot started as @your_bot_username`. Open your bot in Telegram, press **Start**
and follow the welcome questions. Stop it with `Ctrl+C`.

### Step 5 (recommended): run the tests

```bash
python -m unittest discover -s tests -v      # Windows: py -m unittest ...
```

These cover the message parser, categories, income splitting, balances, statistics, Excel and
chart generation, tip scheduling and the translation files.

---

## 2. Keep it running 24/7 (hosting)

The bot uses **long polling**: it connects out to Telegram. You do **not** need a domain,
SSL certificate or open ports. It only needs a computer that stays on and has internet.
Run **only one copy** at a time with the same token, otherwise Telegram answers with
`Conflict: terminated by other getUpdates request`.

### Option A: a small Linux server (VPS), recommended

Any cheap Ubuntu or Debian VPS is enough (1 vCPU, 512 MB to 1 GB RAM).

```bash
sudo adduser --system --group --home /opt/moneymate moneymate
sudo apt install -y python3-venv sqlite3 unzip
# upload moneymate_bot.zip to the server (scp / sftp), then:
sudo unzip moneymate_bot.zip -d /opt
sudo cp -a /opt/moneymate_bot/. /opt/moneymate/ && sudo rm -r /opt/moneymate_bot
sudo chown -R moneymate:moneymate /opt/moneymate
cd /opt/moneymate
sudo -u moneymate python3 -m venv .venv
sudo -u moneymate .venv/bin/pip install -r requirements.txt
sudo -u moneymate cp .env.example .env && sudo -u moneymate nano .env     # paste your token
sudo cp deploy/moneymate.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now moneymate
```

Check it: `sudo systemctl status moneymate`, and watch logs with `journalctl -u moneymate -f`.
The service restarts automatically after crashes and reboots.

### Option B: Docker

```bash
cp .env.example .env      # put your token in it
docker compose up -d --build
docker compose logs -f
```

The database is stored in `./data`, outside the container, so updates do not erase it.

### Option C: a cloud app platform (Railway, Render, Fly.io and similar)

Deploy this folder as a worker/background service (not a web service) with the start command
`python bot.py`, and set `BOT_TOKEN` as an environment variable. **Important:** the bot stores
data in a SQLite file, so attach a **persistent volume** and point `DB_PATH` at it
(for example `DB_PATH=/data/moneymate.db`). Without a volume, many platforms wipe the file on
every deploy and your users' data is lost. Check each platform's current pricing and limits.

### Option D: your own computer or a Raspberry Pi

Fine for testing or personal use. The bot is only online while that computer is on and connected.

### Backups

Everything lives in one file: `data/moneymate.db`. Back it up regularly.
`deploy/backup.sh` makes a safe copy while the bot is running and keeps the last 14
(schedule it with `crontab -e`, for example `0 3 * * * /opt/moneymate/deploy/backup.sh`).

### Updating

Stop the bot, replace the code files (keep `.env` and `data/`), run `pip install -r requirements.txt`
again if `requirements.txt` changed, start the bot. The database is created and extended
automatically on start.

### Security and privacy checklist

- Never share or commit the token. If it leaks, send `/revoke` to @BotFather to get a new one.
- The bot stores people's income, debts and spending on **your server**. Protect the server
  (SSH keys, updates, firewall), keep backups private, and tell your users what you store.
  The welcome message already explains this and `/deletedata` lets users erase everything.
  If you offer the bot publicly, check the data-protection rules that apply where you and
  your users live.

---

## 3. Commands

| Command | What it does |
|---|---|
| `/start` | Welcome and setup questions |
| *(just type)* `coffee 15000` | Add an expense. A bare number starts the guided flow |
| `+1000000 salary` or `/income` | Add income and split it into buckets |
| `/undo` | Remove the last entry (expense or income) |
| `/today` `/week` `/month` | Spending summaries |
| `/balance` | Money left in Needs / Wants / Savings |
| `/show <category or bucket> [period] [over N]` | List expenses, e.g. `/show transport last month` |
| `/categories` | Category menu with this month's totals |
| `/search <text>` | Find expenses by note |
| `/top` / `/top categories` | Biggest expenses / categories |
| `/stats` | Spending habits and insights |
| `/chart` | Charts by month, category, weekday |
| `/export [period]` | Excel report |
| `/settings` `/profile` `/language` `/currency` `/timezone` | Personal settings |
| `/setsplit 80 10 10` | Your usual income split |
| `/tips on\|off` `/tiptime 09:00` `/tip` | Daily tips |
| `/newcategory Pets 🐶` | Custom category |
| `/deletedata` | Erase all your data |
| `/help` `/cancel` | Help / stop the current step |
| `/admin` | Owner statistics (needs `ADMIN_IDS`) |

Periods understood by `/show`, `/top` and `/export`: `today`, `week`, `month`, `last month`,
`year`, `2026`, `all`, or a month name in English, Russian or Uzbek (`october`, `октябрь`, `oktabr`).
Dates in messages: `yesterday`, `вчера`, `kecha`, `12.11`, `12.11.2026`, `2026-11-12`.

---

## 4. Customising

| I want to... | Edit |
|---|---|
| Change any text, or fix a translation | `app/locales/en.json`, `ru.json`, `uz.json` (keep the `{placeholders}` unchanged; the tests check this) |
| Make words map to a category | `KEYWORDS` in `app/categories.py` |
| Change default categories or their buckets | `DEFAULT_CATEGORIES` in `app/categories.py` (applies to new users) |
| Add or change daily tips | `app/data/tips.json` (give each tip a new `id` and all three languages) |
| Change split templates, buckets or page size | `app/config.py` |
| Change the welcome picture | Replace `assets/banner.png` (or edit and run `assets/make_banner.py`) |
| Change when reports and reminders go out | `app/due.py` |

## 5. Troubleshooting

| Problem | Fix |
|---|---|
| `BOT_TOKEN is not set` | Create `.env` next to `bot.py` with `BOT_TOKEN=...` |
| `Unauthorized` / `401` | The token is wrong or was revoked. Copy it again from @BotFather |
| `Conflict: terminated by other getUpdates request` | Another copy of the bot is running with the same token. Stop it |
| Time zone error on Windows | `pip install tzdata` (it is in `requirements.txt`) |
| Tips or reports arrive at the wrong hour | Set the right zone with `/timezone`; messages follow each user's own local time |
| Bot does not answer in a group | By design the bot works in private chats only |
| Charts show empty boxes instead of letters | Install a font with Latin and Cyrillic letters (DejaVu Sans) |

## 6. Project layout

```
bot.py                 entry point (python bot.py)
app/
  config.py            settings, .env loading
  db.py                SQLite schema and helpers
  service.py           business logic (users, expenses, income splits, balances)
  parser.py            "taxi 22k yesterday" -> amount, date, note
  categories.py        default categories and multilingual keywords
  period.py            "last month", "october" -> date ranges
  stats.py             totals and habit insights
  charts.py            PNG charts       exports.py   Excel reports
  tips.py              daily tip selection        due.py        who is due for tip/report/reminder
  scheduler.py         background jobs (tips, monthly reports, reminders)
  i18n.py, locales/    translations
  handlers/            Telegram handlers: onboarding, expenses, income, reports, settings
assets/                banner.png, logo.png and the script that draws them
deploy/                systemd service and backup script
tests/                 unit tests
```

## 7. Status and honesty notes

- The logic (parsing, splitting, balances, statistics, Excel, charts, scheduling, translations)
  is covered by automated tests, and the whole bot flow was exercised in simulated
  conversations in all three languages. The very first connection to the real Telegram servers
  could not be tried while writing the code, so **your first run is the final test**. If you see
  an error, copy the traceback and ask for a fix.
- The Russian and Uzbek texts were written by an AI. Have a native speaker read them before
  you share the bot widely, especially the financial wording; they are plain JSON files, easy to edit.
- The daily tips are general education, not financial advice.
