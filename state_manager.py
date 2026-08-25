import json
import subprocess
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict
from settings import Settings

logger = logging.getLogger(__name__)

KNOWN_FIELDS = {"alerted_bets", "bet_log"}


@dataclass
class BotState:
    alerted_bets: Dict[str, str] = field(default_factory=dict)
    # key = f"{game_id}:{market}:{selection}" -> ISO timestamp alerted

    bet_log: list = field(default_factory=list)
    # list of dicts: {timestamp, teams, market, selection, odds, confidence, result: "pending"}


def load_state(settings: Settings) -> BotState:
    path = Path(settings.STATE_FILE)
    if not path.exists():
        logger.info("State file not found — starting fresh.")
        return BotState()
    try:
        raw = json.loads(path.read_text())
        filtered = {k: v for k, v in raw.items() if k in KNOWN_FIELDS}
        return BotState(**filtered)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to load state file (using fresh state): {e}")
        return BotState()


def save_state(state: BotState, settings: Settings) -> None:
    """Write state locally, then commit + push directly with git."""
    path = Path(settings.STATE_FILE)
    try:
        path.write_text(json.dumps(asdict(state), indent=2))
    except OSError as e:
        logger.error(f"Failed to write state file: {e}")
        return

    if not settings.GITHUB_TOKEN or not settings.GITHUB_REPOSITORY:
        logger.warning("GitHub credentials missing — state saved locally only, not committed.")
        return

    try:
        remote = f"https://x-access-token:{settings.GITHUB_TOKEN}@github.com/{settings.GITHUB_REPOSITORY}.git"
        subprocess.run(["git", "config", "user.email", "football-bot@actions"], check=True)
        subprocess.run(["git", "config", "user.name", "Football Bot"], check=True)
        subprocess.run(["git", "remote", "set-url", "origin", remote], check=True)
        subprocess.run(["git", "add", settings.STATE_FILE], check=True)

        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if diff.returncode != 0:
            subprocess.run(["git", "pull", "--rebase", "--autostash"], check=True)
            subprocess.run(
                ["git", "commit", "-m",
                 f"chore: update football bot state [{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}]"],
                check=True
            )
            subprocess.run(["git", "push"], check=True)
            logger.info("State committed to GitHub successfully.")
        else:
            logger.info("No state changes to commit.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Git commit/push failed: {e}")


def prune_old_alerts(state: BotState, ttl_hours: int) -> BotState:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    pruned = {}
    for k, v in state.alerted_bets.items():
        try:
            if datetime.fromisoformat(v) > cutoff:
                pruned[k] = v
        except ValueError:
            continue  # drop corrupted timestamp entries
    return BotState(alerted_bets=pruned, bet_log=state.bet_log)


def already_alerted(state: BotState, bet_key: str) -> bool:
    return bet_key in state.alerted_bets


def mark_alerted(state: BotState, bet_key: str) -> None:
    state.alerted_bets[bet_key] = datetime.now(timezone.utc).isoformat()


def log_bet(state: BotState, bet) -> None:
    """Log every alerted bet so you can review win/loss performance later."""
    state.bet_log.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "teams": f"{bet.home_team} vs {bet.away_team}",
        "market": bet.market,
        "selection": bet.selection,
        "odds": bet.best_odds,
        "bookmaker": bet.best_bookmaker,
        "edge": round(bet.edge, 1),
        "confidence": bet.confidence,
        "result": "pending",   # you update this manually later: win / loss
    })
