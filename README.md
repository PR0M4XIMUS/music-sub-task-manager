# Subs Tasks Manager Bot

Telegram bot to track shared subscription payments, collect proofs, and send monthly reminders.

## Features
- Members: `/start`, `/pay <amount> <months>`, send proof, `/history`
- Admin: `/status`, `/setmute <user> <months>`, `/setamount <value>`, `/setday <1-28>`,
  `/proof <user>`, `/addmember <user>`, `/remove <user>`, `/export`

## Quick Start

1. **Revoke** the leaked token in BotFather and generate a new one.
2. Create a `.env` next to `docker-compose.yml`:
