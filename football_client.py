import requests
import logging
import time
from dataclasses import dataclass
from typing import List
from settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class Outcome:
    name: str
    price: float


@dataclass
class Market:
    key: str
    outcomes: List[Outcome]


@dataclass
class Bookmaker:
    key: str
    title: str
    markets: List[Market]


@dataclass
class FootballGame:
    id: str
    sport_key: str
    sport_title: str
    home_team: str
    away_team: str
    commence_time: str
    bookmakers: List[Bookmaker]


class FootballClient:
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 2

    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def fetch_games(self, league: str) -> List[FootballGame]:
        """Fetch upcoming games with odds for a given league. Retries on transient errors."""
        url = f"{self.settings.ODDS_API_BASE_URL}/sports/{league}/odds"
        params = {
            "apiKey": self.settings.ODDS_API_KEY,
            "regions": self.settings.REGIONS,
            "markets": self.settings.MARKETS,
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, params=params, timeout=15)

                if resp.status_code == 422:
                    logger.warning(f"[{league}] Not available on your API tier — skipping.")
                    return []

                if resp.status_code == 401:
                    logger.error(f"[{league}] Invalid API key. Check ODDS_API_KEY secret.")
                    return []

                if resp.status_code == 429:
                    logger.warning(f"[{league}] Rate limited — waiting before retry.")
                    time.sleep(self.RETRY_DELAY_SECONDS * attempt)
                    continue

                resp.raise_for_status()
                raw = resp.json()

                remaining = resp.headers.get("x-requests-remaining", "N/A")
                logger.info(f"[{league}] {len(raw)} games returned | Credits remaining: {remaining}")

                games = []
                for g in raw:
                    parsed = self._parse_game(g)
                    if parsed is not None:
                        games.append(parsed)
                return games

            except requests.Timeout:
                logger.warning(f"[{league}] Timeout on attempt {attempt}/{self.MAX_RETRIES}")
                time.sleep(self.RETRY_DELAY_SECONDS)
            except requests.ConnectionError:
                logger.warning(f"[{league}] Connection error on attempt {attempt}/{self.MAX_RETRIES}")
                time.sleep(self.RETRY_DELAY_SECONDS)
            except requests.HTTPError as e:
                logger.error(f"[{league}] HTTP error: {e}")
                return []
            except Exception as e:
                logger.error(f"[{league}] Unexpected error: {e}")
                return []

        logger.error(f"[{league}] Failed after {self.MAX_RETRIES} attempts — skipping this league.")
        return []

    def fetch_all_leagues(self) -> List[FootballGame]:
        all_games: List[FootballGame] = []
        for league in self.settings.LEAGUES:
            games = self.fetch_games(league)
            all_games.extend(games)
        logger.info(f"Total games fetched across all leagues: {len(all_games)}")
        return all_games

    def _parse_game(self, raw: dict):
        """Returns None (and logs) instead of crashing on malformed data."""
        try:
            bookmakers = []
            for bk in raw.get("bookmakers", []):
                markets = []
                for mk in bk.get("markets", []):
                    outcomes = []
                    for o in mk.get("outcomes", []):
                        try:
                            outcomes.append(Outcome(name=o["name"], price=float(o["price"])))
                        except (KeyError, TypeError, ValueError):
                            continue  # skip malformed outcome, don't kill the whole game
                    if outcomes:
                        markets.append(Market(key=mk["key"], outcomes=outcomes))
                if markets:
                    bookmakers.append(Bookmaker(key=bk["key"], title=bk["title"], markets=markets))

            return FootballGame(
                id=raw["id"],
                sport_key=raw["sport_key"],
                sport_title=raw.get("sport_title", raw["sport_key"]),
                home_team=raw["home_team"],
                away_team=raw["away_team"],
                commence_time=raw["commence_time"],
                bookmakers=bookmakers,
            )
        except (KeyError, TypeError) as e:
            logger.warning(f"Skipping malformed game record: {e}")
            return None
