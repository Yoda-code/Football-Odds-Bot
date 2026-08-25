import logging
import sys
from settings import load_settings
from football_client import FootballClient
from analyzer import FootballAnalyzer
from notifier import FootballNotifier
from state_manager import (
    load_state, save_state, prune_old_alerts,
    already_alerted, mark_alerted, log_bet,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=== Football Analytics Bot starting ===")

    try:
        settings = load_settings()
    except KeyError as e:
        logger.critical(f"Missing required environment variable: {e}")
        sys.exit(1)

    state = load_state(settings)
    state = prune_old_alerts(state, settings.ALERTED_TTL_HOURS)

    client = FootballClient(settings)
    notifier = FootballNotifier(settings)

    try:
        games = client.fetch_all_leagues()
    except Exception as e:
        logger.critical(f"Fatal error fetching games: {e}")
        notifier.send_warning(f"Bot crashed while fetching games: {e}")
        sys.exit(1)

    total_games = len(games)
    logger.info(f"Total games available: {total_games}")

    if total_games < settings.MIN_GAMES_REQUIRED:
        msg = (
            f"Only {total_games} game(s) found across all leagues "
            f"(minimum: {settings.MIN_GAMES_REQUIRED}). Skipping analysis."
        )
        logger.warning(msg)
        notifier.send_warning(msg)
        save_state(state, settings)
        return

    try:
        analyzer = FootballAnalyzer(settings)
        value_bets = analyzer.analyze(games)
    except Exception as e:
        logger.critical(f"Fatal error during analysis: {e}")
        notifier.send_warning(f"Bot crashed during analysis: {e}")
        save_state(state, settings)
        sys.exit(1)

    logger.info(f"Value bets detected: {len(value_bets)}")

    new_alerts = 0
    for bet in value_bets:
        bet_key = f"{bet.game_id}:{bet.market}:{bet.selection}"
        if not already_alerted(state, bet_key):
            notifier.send_value_bet(bet)
            mark_alerted(state, bet_key)
            log_bet(state, bet)
            new_alerts += 1
        else:
            logger.info(f"Already alerted: {bet.home_team} vs {bet.away_team} | {bet.selection}")

    leagues_scanned = list({g.sport_title for g in games})
    notifier.send_summary(
        total_games=total_games,
        value_bets_found=len(value_bets),
        leagues_scanned=leagues_scanned,
        new_alerts_sent=new_alerts,
    )

    save_state(state, settings)
    logger.info(f"=== Run complete | Games: {total_games} | Alerts: {new_alerts} ===")


if __name__ == "__main__":
    main()
