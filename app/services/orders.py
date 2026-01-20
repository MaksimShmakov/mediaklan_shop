import urllib.parse
from datetime import date, datetime, time
from typing import Optional

from app.core.config import ORDER_STATUSES
from app.models import Order


def parse_date_input(
    value: Optional[str], end_of_day: bool
) -> Optional[datetime]:
    if not value:
        return None
    try:
        if "T" in value:
            return datetime.fromisoformat(value)
        parsed_date = date.fromisoformat(value)
        return datetime.combine(
            parsed_date, time.max if end_of_day else time.min
        )
    except ValueError:
        return None


def build_order_filters(
    status_filter: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[list, Optional[str], Optional[datetime], Optional[datetime]]:
    filters: list = []
    resolved_status = status_filter if (
        status_filter in ORDER_STATUSES
    ) else None
    start_dt = parse_date_input(date_from, end_of_day=False)
    end_dt = parse_date_input(date_to, end_of_day=True)
    if resolved_status:
        filters.append(Order.status == resolved_status)
    if start_dt:
        filters.append(Order.created_at >= start_dt)
    if end_dt:
        filters.append(Order.created_at <= end_dt)
    return filters, resolved_status, start_dt, end_dt


def build_export_url(
    status_filter: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
) -> str:
    params = {}
    if status_filter:
        params["status"] = status_filter
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    query = urllib.parse.urlencode(params)
    return f"/admin/orders/export?{query}" if query else "/admin/orders/export"
