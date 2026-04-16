# Household

A personal home automation system for the Sherenkov family. Alfred, the household's AI butler, orchestrates a growing staff of specialized agents. Currently, the household employs Miles — a travel attaché who hunts weekend flight deals from Atlanta and reports them via Telegram.

---

## How it works

**Alfred** is the orchestrator. He dispatches **Miles** twice a day to search for weekend getaways departing ATL for 2 adults and 1 child (budget $200–500 round trip). Miles checks the next 8 weekends across 300+ destinations (60 per rotating batch), flags US holiday windows, and sends a Telegram message if deals are found.

Three trip windows are evaluated for each weekend:

| Window | Departure | Return |
|--------|-----------|--------|
| Standard | Fri after 17:00 | Sun before 23:00 |
| Long Thu | Thu any time | Sun before 23:00 |
| Long Mon | Fri after 17:00 | Mon before 23:00 |

Holiday Fridays and Mondays are automatically detected and surfaced in the message.

---

## Project structure

```
.claude/                        Claude Code configuration
  agents/
    alfred.md                   Alfred AI persona — household orchestrator
    miles.md                    Miles AI persona — travel attaché
  skills/find-flights/          /find-flights on-demand skill

agents/                         Python automation (runs in GitHub Actions)
  alfred/                       Shared library — Alfred's voice & vocabulary
    persona.py
  miles/                        Miles' flight search bot
    main.py                     Entry point
    flight_search.py            Search + filter logic
    windows.py                  Trip window generator + US holiday calendar
    airports.py                 OurAirports data loader + batch rotation
    google_flights.py           fast-flights wrapper
    telegram_notifier.py        Message formatting + Telegram delivery

.github/workflows/
  household-flights.yml         Twice-daily GitHub Actions schedule
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/ysherenkova/household.git
cd household
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID_YULIIA=...
TELEGRAM_CHAT_ID_IVAN=...
```

See `.env.example` for step-by-step instructions on creating the Telegram bot and finding chat IDs.

### 3. Run Miles locally

```bash
cd agents/miles
python main.py
```

To test without sending Telegram messages, set the three variables to dummy values — the search and filter logic will still run and log to stdout.

---

## Automated schedule (GitHub Actions)

Miles runs automatically twice a day via `.github/workflows/household-flights.yml`:

| Run | Time (ET) | Time (UTC) |
|-----|-----------|------------|
| Morning | 09:00 | 13:00 |
| Evening | 21:00 | 01:00 |

You can also trigger a run manually from the **Actions** tab → **Household — dispatches Miles** → **Run workflow**.

### Required GitHub secrets

Add these in **Settings → Secrets and variables → Actions**:

| Secret | Description |
|--------|-------------|
| `TELEGRAM_BOT_TOKEN` | BotFather token |
| `TELEGRAM_CHAT_ID_YULIIA` | Yuliia's Telegram chat ID |
| `TELEGRAM_CHAT_ID_IVAN` | Ivan's Telegram chat ID |

---

## On-demand search with Claude Code

If you have Claude Code, you can trigger an immediate search without waiting for the scheduled run:

```
/find-flights
```

Alfred will dispatch Miles on the spot and report findings in the conversation.

---

## Adding a new household agent

1. Create `agents/<name>/` with `main.py` and a `telegram_notifier.py` that imports from `agents/alfred/persona.py`
2. Register the agent in `agents/alfred/__init__.py` and `agents/alfred/persona.py`
3. Add a GitHub Actions workflow in `.github/workflows/`
4. Create `.claude/agents/<name>.md` for the Claude persona
5. Optionally add `.claude/skills/<name>/SKILL.md` for manual invocation

See `.claude/agents/alfred.md` for the full onboarding guide.
