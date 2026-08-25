from dataclasses import dataclass, field
from typing import FrozenSet


@dataclass(frozen=True)
class Settings:
    # ── Telegram ──────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_CHAT_ID: str

    # ── The Odds API ──────────────────────────────────────────
    ODDS_API_KEY: str
    ODDS_API_BASE_URL: str = "https://api.the-odds-api.com/v4"

    # ── Football Leagues (The Odds API sport keys) ────────────
    LEAGUES: FrozenSet[str] = field(default_factory=lambda: frozenset({
        "soccer_epl",
        "soccer_uefa_champs_league",
        "soccer_spain_la_liga",
        "soccer_germany_bundesliga",
        "soccer_italy_serie_a",
        "soccer_france_ligue_one",
        "soccer_fifa_world_cup",
    }))

    # ── Bookmaker Regions ─────────────────────────────────────
    REGIONS: str = "us,eu,uk"

    # ── Markets to scan ───────────────────────────────────────
    MARKETS: str = "h2h,totals"

    # ── Reliability Filters (mirrors Tennis bot) ──────────────
    MIN_EDGE_PERCENT: float = 3.0        # Minimum value edge to alert
    MIN_BOOKMAKERS: int = 3              # Game needs 3+ books pricing it
    MIN_VALUE_BOOKS: int = 2             # 2+ books must independently show value
    MIN_TRUE_PROBABILITY: float = 0.35   # Fair win chance must be at least this
    MIN_ODDS: float = 1.50               # Skip extreme favorites
    MAX_ODDS: float = 5.00               # Skip extreme longshots (wider than tennis — draws exist)
    MIN_GAMES_REQUIRED: int = 3          # Suppress run if too few games found

    # ── State ─────────────────────────────────────────────────
    STATE_FILE: str = "football_state.json"
    ALERTED_TTL_HOURS: int = 24

    # ── GitHub (for state commits) ────────────────────────────
    GITHUB_TOKEN: str = ""
    GITHUB_REPOSITORY: str = ""   # e.g. "Shalom-Okpapi/football-analytics"


def load_settings() -> Settings:
    import os
    return Settings(
        TELEGRAM_BOT_TOKEN=os.environ["TELEGRAM_BOT_TOKEN"],
        TELEGRAM_CHAT_ID=os.environ["TELEGRAM_CHAT_ID"],
        ODDS_API_KEY=os.environ["ODDS_API_KEY"],
        GITHUB_TOKEN=os.environ.get("GITHUB_TOKEN", ""),
        GITHUB_REPOSITORY=os.environ.get("GITHUB_REPOSITORY", ""),
    )
