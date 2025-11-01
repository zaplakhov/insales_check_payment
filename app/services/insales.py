from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx

from ..config import settings


@dataclass
class InsalesAccountInfo:
    paid_till: Optional[date]


class InsalesClient:
    """Client for interacting with the InSales API."""

    def __init__(self, timeout: int = settings.insales_timeout) -> None:
        self._timeout = timeout

    async def fetch_account(self, *, domain: str, api_key: str, password: str) -> InsalesAccountInfo:
        url = f"https://{domain}/admin/account.json"
        auth = (api_key, password)
        async with httpx.AsyncClient(timeout=self._timeout, auth=auth) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()

        account_data = {}
        if isinstance(payload, dict):
            # InSales может отдавать данные либо в корне, либо вложенными в account
            nested = payload.get("account")
            account_data = nested if isinstance(nested, dict) else payload

        paid_till_str = account_data.get("paid_till")
        paid_till = date.fromisoformat(paid_till_str) if paid_till_str else None
        return InsalesAccountInfo(paid_till=paid_till)
