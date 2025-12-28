# AI Coding Agent Instructions for Alex Phuket Bot

## Project Overview
This is a Telegram bot for personalized tour recommendations in Phuket, Thailand. The bot collects user details (group composition, pregnancy, health concerns) and filters tours from a CSV database based on strict safety rules.

## Architecture
- **Main Bot**: `bot.py` - Telegram conversation handlers, user flow management
- **Data Parsing**: `parser_functions.py` - Extract adults/children/pregnancy from free text, age conversions (months internally)
- **Configuration**: `config.py` - Bot stages, question types, error types for analytics
- **Analytics**: `analytics/logger.py` - SQLite logging of user actions, tour views, questions
- **Data Source**: CSV file with tour details and safety tags (e.g., `#нельзя_беременным`, `#дети_от_1_года`)

## Key Patterns
- **Age Handling**: Store ages as months (`age_to_months()`), display as years with Russian pluralization (`format_age_months()`)
- **Safety Filtering**: Strict rules - no sea tours for pregnant/pregnant, children <1yr; check CSV "Теги (Безопасность)" column
- **Conversation Flow**: 5 states (CATEGORY → QUALIFICATION → CONFIRMATION → TOUR_DETAILS → QUESTION)
- **Analytics Stages**: Use `BOT_STAGES` from config for consistent logging
- **Error Handling**: Log to `ERROR_TYPES` categories, never crash on user input

## Development Workflow
- **Run Bot**: `python bot.py` (requires `.env` with `TELEGRAM_BOT_TOKEN`)
- **Test Parsing**: Run `test_fixed_parser.py` for parser validation
- **Database**: Auto-initializes on startup; use `create_tables.py` for extended analytics schema
- **Dependencies**: `python-telegram-bot`, `python-dotenv`, `pandas` (for stats export)

## Code Style
- Russian comments/variables for domain logic
- Async handlers for Telegram interactions
- SQLite with JSON for complex data (session_data)
- CSV delimiter `;` with UTF-8-BOM handling

## Safety Rules (Critical)
- Pregnant: No sea tours, even catamarans
- Children <12 months: No sea tours
- Health issues: Avoid `#проблемы_спины`, `#трясет` tags
- Always confirm group details before recommendations

## Common Tasks
- Adding tours: Update CSV with safety tags
- New filters: Modify `filter_tours_by_safety()` in test files first
- Analytics: Extend `AnalyticsLogger` methods for new metrics</content>
<parameter name="filePath">/workspaces/alex-phuket-bot/.github/copilot-instructions.md