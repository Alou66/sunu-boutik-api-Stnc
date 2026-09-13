from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.modules.statistics.statistics_repository import StatisticsRepository


class StatisticsValidationError(Exception):
    pass


class StatisticsService:
    def __init__(self, db: Session):
        self._db = db
        self._repo = StatisticsRepository(db)

    def _parse_period(self, date_from: str, date_to: str) -> tuple[datetime, datetime]:
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d")
            end_day = datetime.strptime(date_to, "%Y-%m-%d")
        except ValueError:
            raise StatisticsValidationError("Dates invalides, format attendu AAAA-MM-JJ")
        if end_day < start:
            raise StatisticsValidationError("La date de fin doit être postérieure ou égale à la date de début")
        # Borne haute exclusive : inclut toute la journée `date_to`.
        return start, end_day + timedelta(days=1)

    def get_statistics(self, shop_id: int, date_from: str, date_to: str) -> dict:
        start, end = self._parse_period(date_from, date_to)

        sales = self._repo.sales_period(shop_id, start, end)
        sales["pending_total"] = sales["invoiced_total"] - sales["collected_total"]
        sales["margin_rate"] = (
            sales["real_profit"] / sales["invoiced_total"] * 100 if sales["invoiced_total"] else 0.0
        )

        return {
            "date_from": date_from,
            "date_to": date_to,
            "stock": self._repo.stock_overview(shop_id),
            "sales": sales,
            "purchases": self._repo.purchases_period(shop_id, start, end),
            "rankings": self._repo.rankings(shop_id),
        }
