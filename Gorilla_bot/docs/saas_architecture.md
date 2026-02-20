# GorillaAI SaaS Autoposting Architecture

## 1) System architecture
- **Bot Layer (aiogram):** handlers, FSM wizards, access control.
- **Application Layer:** navigator service, autopost orchestrator, project wizard logic, permission checks.
- **Data Layer:** PostgreSQL schema (production) + JSON fallback in MVP.
- **Worker Layer:** async scheduler loops for autopost and reminders.
- **AI Layer:** OpenRouter/GPT integration for generation, coaching, analysis.

## 2) Database schema (PostgreSQL)
See `docs/schema.sql`.

## 3) Core handlers
- `/start`, `/menu`, `/access`
- Navigator: onboarding, dashboard, coach mode, reminders, update analysis.
- Autopost: classic channels and SaaS projects wizard.
- AI Help Agent + online psychologist contact.
- Esoteric deep menu with per-system input format guidance.

## 4) Project Wizard (8 steps)
1. Channel connect
2. Topic
3. Style
4. Formatting
5. Frequency
6. Sources
7. GPT preview
8. Start project

## 5) Scheduler
- `autopost_loop`: checks channel-based and project-based autopost schedules.
- `reminder_loop`: sends daily/weekly/monthly navigator plans.

## 6) GPT services
- `ask_llm()` wrapper in `personal_bot/services.py`.
- Reused for assistant, autopost content, navigator analysis, coach mode.

## 7) Permission model
- User-level premium access.
- Group permissions toggle (`write/edit/delete/ban/posts`).
- Project ownership isolation by `user_id`.

## 8) Scalability
- Move from in-memory/JSON to PostgreSQL + Redis queue + worker pool.
- Split handlers by domain (`handlers/navigator.py`, `handlers/projects.py`).
- Add telemetry and rate limiting.
