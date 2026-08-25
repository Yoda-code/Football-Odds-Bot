import logging
import requests
from datetime import datetime, timezone
from typing import List
from analyzer import ValueBet
from settings import Settings

logger = logging.getLogger(__name__)

LEAGUE_FLAGS = {
    "English Premier League": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "UEFA Champions League": "🏆",
    "La Liga": "🇪🇸",
    "Bundesliga": "🇩🇪",
    "Serie A": "🇮🇹",
    "Ligue 1": "🇫🇷",
    "FIFA World Cup": "🌍",
}

MARKET_LABELS = {
    "h2h": "Who Will Win",
    "totals": "Goals (Over/Under)",
}


class FootballNotifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._base = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"

    def send_value_bet(self, bet: ValueBet) -> None:
        flag = LEAGUE_FLAGS.get(bet.sport_title, "⚽")
        market_label = MARKET_LABELS.get(bet.market, bet.market.upper())
        kickoff = self._format_time(bet.commence_time)

        odds_lines = "\n".join(
            f"  • {book}: {odds:.2f}"
            for book, odds in sorted(bet.all_odds.items(), key=lambda x: x[1], reverse=True)[:5]
        )

        msg = (
            f"{flag} <b>GOOD BET FOUND!</b>\n"
            f"{'─' * 30}\n"
            f"⚽ <b>{bet.home_team}</b> vs <b>{bet.away_team}</b>\n"
            f"🏆 League: {bet.sport_title}\n"
            f"⏰ Match starts: {kickoff}\n\n"
            f"📊 <b>Bet Type:</b> {market_label}\n"
            f"🎯 <b>Pick:</b> {bet.selection}\n\n"
            f"💰 <b>Best Odds:</b> {bet.best_odds:.2f} at {bet.best_bookmaker}\n"
            f"📈 <b>Extra Value:</b> +{bet.edge:.1f}%\n"
            f"🔒 <b>Confirmed by:</b> {bet.confirming_books} bookmakers (agree this is good value)\n"
            f"⭐ <b>Confidence Score:</b> {bet.confidence}/100\n"
            f"   (Real chance of winning: {bet.fair_prob * 100:.1f}%,\n"
            f"   but odds pay as if it's only {bet.implied_prob * 100:.1f}%)\n\n"
            f"📚 <b>Odds at other bookmakers:</b>\n{odds_lines}\n\n"
            f"💡 <i>Higher odds = more money if you win.\n"
            f"Always bet only what you can afford to lose.</i>"
        )
        self._send(msg)

    def send_summary(self, total_games: int, value_bets_found: int,
                      leagues_scanned: List[str], new_alerts_sent: int) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        league_list = "\n".join(f"  • {lg}" for lg in sorted(leagues_scanned))

        msg = (
            f"⚽ <b>Football Bot — Scan Report</b>\n"
            f"{'─' * 30}\n"
            f"🕐 Time checked: {now}\n\n"
            f"📋 <b>Leagues we checked:</b>\n{league_list}\n\n"
            f"🔍 Total matches checked: <b>{total_games}</b>\n"
            f"💡 Good bets found: <b>{value_bets_found}</b>\n"
            f"📣 New alerts sent to you: <b>{new_alerts_sent}</b>\n\n"
            f"ℹ️ <i>We only alert you about NEW good bets, and only when\n"
            f"2 or more bookmakers agree it's good value.\n"
            f"If you got 0 alerts, nothing solid was found this time.</i>"
        )
        self._send(msg)

    def send_warning(self, message: str) -> None:
        self._send(
            f"⚠️ <b>Heads Up!</b>\n\n{message}\n\n"
            f"<i>The bot is still running. This is just a notice.</i>"
        )

    def _send(self, text: str) -> None:
        url = f"{self._base}/sendMessage"
        payload = {
            "chat_id": self.settings.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
        except requests.Timeout:
            logger.error("Telegram send timed out.")
        except requests.HTTPError as e:
            logger.error(f"Telegram HTTP error: {e} | Response: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    @staticmethod
    def _format_time(iso_str: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return dt.strftime("%a %d %b %Y, %H:%M UTC")
        except Exception:
            return iso_str
