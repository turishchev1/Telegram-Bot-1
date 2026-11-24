#!/bin/sh
# Safe copy of the live SQLite database (works while the bot is running).
# Example cron entry (every night at 03:00):  0 3 * * * /opt/moneymate/deploy/backup.sh
set -e
cd "$(dirname "$0")/.."
mkdir -p backups
sqlite3 data/moneymate.db ".backup 'backups/moneymate-$(date +%F).db'"
# keep the last 14 backups
ls -1t backups/moneymate-*.db | tail -n +15 | xargs -r rm --
