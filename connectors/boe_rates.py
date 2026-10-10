"""Live Bank of England Bank Rate from the BoE Interactive Statistical Database."""
from __future__ import annotations

import csv
import io
from datetime import datetime

import requests

from core.models import RawItem
from core.skill import Connector as Base

URL = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes"
       "&Datefrom=01/Jan/2023&Dateto=now&SeriesCodes=IUDBEDR&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")


class Connector(Base):
    id = "boe_bank_rate"

    def fetch(self) -> list[RawItem]:
        resp = requests.get(URL, timeout=self.options.get("timeout", 10),
                            headers={"User-Agent": "Mozilla/5.0 (london-office-agent PoC)"})
        resp.raise_for_status()
        rows = list(csv.reader(io.StringIO(resp.text)))
        points = []
        for r in rows[1:]:
            if len(r) < 2 or not r[1].strip():
                continue
            date = datetime.strptime(r[0].strip(), "%d %b %Y").strftime("%Y-%m-%d")
            points.append((date, float(r[1])))
        if not points:
            raise ValueError("BoE response had no data rows")
        # Keep only the days the rate changed, plus the latest reading.
        items, last = [], None
        for date, value in points:
            if value != last:
                items.append(self._item(date, value, "Rate change"))
                last = value
        items.append(self._item(points[-1][0], points[-1][1], "Latest published value"))
        return items

    def _item(self, date, value, note):
        return RawItem(connector=self.id, payload={"date": date, "indicator": "bank_rate", "value": value,
                                                   "unit": "pct", "source_id": "BOE_IADB", "note": note})
