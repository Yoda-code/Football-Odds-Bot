import logging
from dataclasses import dataclass
from typing import List, Dict
from football_client import FootballGame
from settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class ValueBet:
    game_id: str
    home_team: str
    away_team: str
    sport_title: str
    commence_time: str
    market: str
    selection: str
    best_odds: float
    best_bookmaker: str
    implied_prob: float
    fair_prob: float
    edge: float
    confirming_books: int      # how many books independently show value
    confidence: int            # 0-100 score
    all_odds: Dict[str, float]


class FootballAnalyzer:
    def __init__(self, settings: Settings):
        self.s = settings

    def analyze(self, games: List[FootballGame]) -> List[ValueBet]:
        value_bets: List[ValueBet] = []
        for game in games:
            value_bets.extend(self._analyze_game(game))
        value_bets.sort(key=lambda b: b.confidence, reverse=True)
        return value_bets

    def _analyze_game(self, game: FootballGame) -> List[ValueBet]:
        results = []
        h2h_odds: Dict[str, Dict[str, float]] = {}
        totals_odds: Dict[str, Dict[str, float]] = {}

        for bk in game.bookmakers:
            for mk in bk.markets:
                for outcome in mk.outcomes:
                    if outcome.price <= 1.0:
                        continue  # bad/void price, skip
                    target = h2h_odds if mk.key == "h2h" else totals_odds
                    sel = self._normalize_selection(outcome.name, game)
                    target.setdefault(sel, {})[bk.title] = outcome.price

        # Require minimum bookmaker coverage before trusting this game at all
        books_seen = {b.title for b in game.bookmakers}
        if len(books_seen) < self.s.MIN_BOOKMAKERS:
            return []

        if len(h2h_odds) >= 2:
            results.extend(self._find_value(game, "h2h", h2h_odds))
        if totals_odds:
            results.extend(self._find_value(game, "totals", totals_odds))

        return results

    def _normalize_selection(self, name: str, game: FootballGame) -> str:
        if name == game.home_team:
            return "Home"
        elif name == game.away_team:
            return "Away"
        return name

    def _find_value(self, game: FootballGame, market_key: str,
                     odds_map: Dict[str, Dict[str, float]]) -> List[ValueBet]:
        results = []
        selections = list(odds_map.keys())

        avg_odds: Dict[str, float] = {}
        for sel, book_odds in odds_map.items():
            if book_odds:
                avg_odds[sel] = sum(book_odds.values()) / len(book_odds)

        implied = {sel: 1.0 / o for sel, o in avg_odds.items() if o > 1.0}
        total_implied = sum(implied.values())
        if total_implied == 0:
            return []

        fair_probs = {sel: imp / total_implied for sel, imp in implied.items()}

        for sel in selections:
            book_odds = odds_map[sel]
            if not book_odds:
                continue

            fair_p = fair_probs.get(sel, 0)
            if fair_p == 0 or fair_p < self.s.MIN_TRUE_PROBABILITY:
                continue

            # Find every bookmaker that independently shows value (not just the best one)
            confirming = {
                book: odds for book, odds in book_odds.items()
                if (fair_p - (1.0 / odds)) * 100 >= self.s.MIN_EDGE_PERCENT
                and self.s.MIN_ODDS <= odds <= self.s.MAX_ODDS
            }

            if len(confirming) < self.s.MIN_VALUE_BOOKS:
                continue  # not enough independent confirmation — skip, likely a mispriced outlier

            best_book = max(confirming, key=confirming.get)
            best_odds = confirming[best_book]
            best_implied = 1.0 / best_odds
            edge = (fair_p - best_implied) * 100

            confidence = self._confidence_score(
                edge=edge,
                confirming_books=len(confirming),
                total_books=len(book_odds),
                fair_p=fair_p,
            )

            logger.info(
                f"✅ VALUE: {game.home_team} v {game.away_team} | "
                f"{market_key.upper()} | {sel} @ {best_odds:.2f} | "
                f"Edge: {edge:.1f}% | Confirmed by {len(confirming)} books | "
                f"Confidence: {confidence}"
            )

            results.append(ValueBet(
                game_id=game.id,
                home_team=game.home_team,
                away_team=game.away_team,
                sport_title=game.sport_title,
                commence_time=game.commence_time,
                market=market_key,
                selection=sel,
                best_odds=best_odds,
                best_bookmaker=best_book,
                implied_prob=best_implied,
                fair_prob=fair_p,
                edge=edge,
                confirming_books=len(confirming),
                confidence=confidence,
                all_odds=book_odds,
            ))

        return results

    @staticmethod
    def _confidence_score(edge: float, confirming_books: int, total_books: int, fair_p: float) -> int:
        """0-100 score. Rewards: bigger edge, more confirming books, higher true probability."""
        edge_score = min(edge / 15 * 40, 40)                    # up to 40 pts, caps at 15% edge
        book_score = min(confirming_books / max(total_books, 1) * 30, 30)  # up to 30 pts
        prob_score = min(fair_p * 30, 30)                       # up to 30 pts
        return round(edge_score + book_score + prob_score)
