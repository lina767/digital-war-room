"""
ACLED Aggregated Data Downloader.

Downloads real-time weekly aggregated XLSX from acleddata.com (Research-level access)
using cookie-based authentication, then extracts country-specific CSV files.

The download page URL pattern:
  https://acleddata.com/aggregated/aggregated-data-middle-east

The XLSX link pattern (updated weekly by ACLED):
  https://acleddata.com/system/files/YYYY-MM/Middle-East_aggregated_data_up_to-YYYY-MM-DD.xlsx
"""

import csv
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from zipfile import ZipFile

import httpx

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "acled"
FRESHNESS_FILE = DATA_DIR / ".last_download"
STALE_HOURS = 24 * 3  # re-download every 3 days

REGION_PAGES = {
    "middle-east": "https://acleddata.com/aggregated/aggregated-data-middle-east",
}

XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
EXCEL_EPOCH = datetime(1899, 12, 30)

COUNTRY_CSV_MAP = {
    "Iran": "acled_iran_aggregated_current.csv",
    "Israel": "acled_israel_aggregated_current.csv",
    "Palestine": "acled_palestine_aggregated_current.csv",
    "Yemen": "acled_yemen_aggregated_current.csv",
    "Syria": "acled_syria_aggregated_current.csv",
    "Iraq": "acled_iraq_aggregated_current.csv",
    "Lebanon": "acled_lebanon_aggregated_current.csv",
}


def _is_stale() -> bool:
    """Return True if data hasn't been downloaded recently."""
    if not FRESHNESS_FILE.exists():
        return True
    try:
        ts = float(FRESHNESS_FILE.read_text().strip())
        return (time.time() - ts) > STALE_HOURS * 3600
    except Exception:
        return True


def _mark_fresh() -> None:
    FRESHNESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FRESHNESS_FILE.write_text(str(time.time()))


def _login() -> Optional[httpx.Client]:
    email = (os.getenv("ACLED_EMAIL") or "").strip()
    password = (os.getenv("ACLED_PASSWORD") or "").strip()
    if not email or not password:
        logger.info("ACLED aggregated: no credentials for cookie login")
        return None
    client = httpx.Client(follow_redirects=True, timeout=30.0)
    try:
        r = client.post(
            "https://acleddata.com/user/login?_format=json",
            json={"name": email, "pass": password},
            headers={"Content-Type": "application/json"},
        )
        if r.status_code != 200:
            logger.warning("ACLED cookie login failed: HTTP %s", r.status_code)
            client.close()
            return None
        logger.info("ACLED cookie login OK for %s", email)
        return client
    except Exception as e:
        logger.warning("ACLED cookie login error: %s", e)
        client.close()
        return None


def _find_xlsx_url(client: httpx.Client, page_url: str) -> Optional[str]:
    """Scrape the aggregated-data page for the XLSX download link."""
    try:
        r = client.get(page_url)
        if r.status_code != 200:
            return None
        links = re.findall(
            r'href=["\']([^"\']*system/files[^"\']*\.xlsx)["\']',
            r.text,
            re.IGNORECASE,
        )
        return links[0] if links else None
    except Exception as e:
        logger.warning("ACLED page scrape error: %s", e)
        return None


def _download_xlsx(client: httpx.Client, url: str) -> Optional[Path]:
    """Download the XLSX file and save it locally."""
    try:
        r = client.get(url, timeout=120.0)
        if r.status_code != 200 or len(r.content) < 5000:
            logger.warning("ACLED XLSX download failed: HTTP %s, size=%d", r.status_code, len(r.content))
            return None
        fname = url.rsplit("/", 1)[-1]
        path = DATA_DIR / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
        logger.info("ACLED XLSX saved: %s (%d bytes)", path.name, len(r.content))
        return path
    except Exception as e:
        logger.warning("ACLED XLSX download error: %s", e)
        return None


def _parse_xlsx_to_csvs(xlsx_path: Path) -> int:
    """Parse XLSX using raw XML (no pandas needed) and write per-country CSVs.
    Returns the total row count written."""
    try:
        with ZipFile(xlsx_path, "r") as z:
            strings: List[str] = []
            if "xl/sharedStrings.xml" in z.namelist():
                with z.open("xl/sharedStrings.xml") as f:
                    for si in ET.parse(f).getroot().findall(f"{{{XLSX_NS}}}si"):
                        t = si.find(f"{{{XLSX_NS}}}t")
                        strings.append(t.text if t is not None else "")

            country_rows: Dict[str, List[Dict[str, str]]] = {c: [] for c in COUNTRY_CSV_MAP}
            col_map = {
                "A": "week",
                "B": "region",
                "C": "country",
                "D": "admin1",
                "E": "event_type",
                "F": "sub_event_type",
                "G": "events",
                "H": "fatalities",
                "I": "population_exposure",
                "J": "disorder_type",
                "L": "centroid_lat",
                "M": "centroid_lon",
            }

            with z.open("xl/worksheets/sheet1.xml") as f:
                for _event, elem in ET.iterparse(f):
                    if elem.tag != f"{{{XLSX_NS}}}row":
                        continue
                    if elem.get("r") == "1":
                        elem.clear()
                        continue
                    cells = elem.findall(f"{{{XLSX_NS}}}c")
                    vals: Dict[str, str] = {}
                    for c in cells:
                        ref = c.get("r", "")
                        col_letter = "".join(ch for ch in ref if ch.isalpha())
                        field = col_map.get(col_letter)
                        if not field:
                            continue
                        t = c.get("t")
                        v_el = c.find(f"{{{XLSX_NS}}}v")
                        val = v_el.text if v_el is not None else ""
                        if t == "s" and val.isdigit():
                            idx = int(val)
                            val = strings[idx] if idx < len(strings) else val
                        vals[field] = val

                    country = vals.get("country", "")
                    if country not in COUNTRY_CSV_MAP:
                        elem.clear()
                        continue

                    week_serial = vals.get("week", "")
                    try:
                        week_date = EXCEL_EPOCH + timedelta(days=int(week_serial))
                        vals["week"] = week_date.strftime("%Y-%m-%d")
                    except (ValueError, TypeError):
                        pass

                    country_rows[country].append(vals)
                    elem.clear()

        total = 0
        fields = [
            "week",
            "admin1",
            "event_type",
            "sub_event_type",
            "events",
            "fatalities",
            "disorder_type",
            "centroid_lat",
            "centroid_lon",
        ]
        for country, fname in COUNTRY_CSV_MAP.items():
            rows = country_rows.get(country, [])
            if not rows:
                continue
            csv_path = DATA_DIR / fname
            with open(csv_path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
            total += len(rows)
            logger.info("ACLED CSV: %s -> %d rows", fname, len(rows))

        return total
    except Exception as e:
        logger.warning("ACLED XLSX parse error: %s", e)
        return 0


def refresh_acled_aggregated(force: bool = False) -> bool:
    """Download and parse latest ACLED aggregated data if stale.
    Returns True if new data was written."""
    if not force and not _is_stale():
        logger.debug("ACLED aggregated: data still fresh, skipping download")
        return False

    client = _login()
    if not client:
        return False

    try:
        for region, page_url in REGION_PAGES.items():
            xlsx_url = _find_xlsx_url(client, page_url)
            if not xlsx_url:
                logger.warning("ACLED aggregated: no XLSX link found for %s", region)
                continue
            xlsx_path = _download_xlsx(client, xlsx_url)
            if not xlsx_path:
                continue
            total = _parse_xlsx_to_csvs(xlsx_path)
            if total > 0:
                _mark_fresh()
                logger.info("ACLED aggregated refresh complete: %d total rows for %s", total, region)
                return True
        return False
    finally:
        client.close()
