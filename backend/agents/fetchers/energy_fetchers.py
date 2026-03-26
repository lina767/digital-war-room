"""
ENERGY / Commodities Agent – commodity indices, food & fertilizer.
Fetches: oil (EIA then FRED then Alpha Vantage), food (FRED then Alpha Vantage),
FAO Food Price Index, World Bank fertilizer prices (global), and optional **World Bank
country macro** indicators (GDP, CPI, electricity access, poverty headcount) for the
conflict-mapped ISO3 — open data, no API key.
Computes food_security_risk. Rule-based score from price volatility. No LLM.
(AGSI+ removed – was unreliable.)
"""

import asyncio
import csv
import io
import logging
import os
from typing import Any, Dict, List, Optional

import httpx


logger = logging.getLogger(__name__)

ALPHAVANTAGE_URL = "https://www.alphavantage.co/query"
EIA_BASE = "https://api.eia.gov/v2/seriesid"
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
# EIA spot price series (daily)
EIA_BRENT_SERIES = "PET.RBRTE.D"
EIA_WTI_SERIES = "PET.RWTC.D"
# FRED: oil daily, food monthly
FRED_OIL_SERIES = [("DCOILBRENTEU", "BRENT", "Brent crude"), ("DCOILWTICO", "WTI", "WTI crude")]
FRED_FOOD_SERIES = [
    ("PWHEAMTUSDM", "WHEAT", "Wheat"),
    ("PMAIZMTUSDM", "CORN", "Corn"),
    ("PSOYBUSDM", "SOYBEAN", "Soybean"),
]

OIL_SYMBOLS = [
    ("BRENT", "Brent crude"),
    ("WTI", "WTI crude"),
]

FOOD_SYMBOLS = [
    ("WHEAT", "Wheat"),
    ("CORN", "Corn"),
    ("SOYBEAN", "Soybean"),
]

COMMODITY_SYMBOLS = OIL_SYMBOLS + FOOD_SYMBOLS

# FAO Food Price Index CSV (free, monthly). FAO may change the filename (e.g. _mar, _apr); override via FAO_FPI_URL env if 404.
FAO_FPI_URL = os.getenv(
    "FAO_FPI_URL",
    "https://www.fao.org/media/docs/worldfoodsituationlibraries/default-document-library/food_price_indices_data_csv_mar.csv",
)

# World Bank commodity prices API (free, monthly)
WORLD_BANK_COMMODITIES_URL = "https://api.worldbank.org/v2/country/WLD/indicator"
WORLD_BANK_BASE = "https://api.worldbank.org/v2/country"
UREA_INDICATOR = "COMMODITY.FERTILIZER.UREA"
DAP_INDICATOR = "COMMODITY.FERTILIZER.DAP"

# Country-level open macro (World Bank Open Data) — mapped from conflict string
WB_MACRO_INDICATORS: List[tuple[str, str, str]] = [
    ("NY.GDP.MKTP.KD.ZG", "gdp_growth_pct", "GDP growth (annual %)"),
    ("FP.CPI.TOTL.ZG", "inflation_cpi_pct", "Inflation, consumer prices (annual %)"),
    ("EG.ELC.ACCS.ZS", "electricity_access_pct", "Access to electricity (% of population)"),
    # Humanitarian / development stress (latest available year per WB)
    ("SI.POV.DDAY", "poverty_headcount_pct", "Poverty headcount at $1.90/day (% pop)"),
]

# Countries heavily exposed to food imports via Hormuz / Bab el-Mandeb
EXPOSED_COUNTRIES = ["Egypt", "Yemen", "Somalia", "Djibouti", "Ethiopia", "Sudan"]

# Normalised conflict slug (dashboard keys) → ISO3 — matches CONFLICT_CENTERS / dropdown labels
_EXACT_CONFLICT_TO_WB_ISO3: Dict[str, str] = {
    "iran": "IRN",
    "us-iran": "IRN",
    "middle-east": "IRN",
    "hezbollah": "LBN",
    "houthis": "YEM",
    "ukraine": "UKR",
    "israel-palestine": "ISR",
    "lebanon": "LBN",
    "taiwan-strait": "TWN",
    "sudan": "SDN",
    "yemen": "YEM",
    "myanmar": "MMR",
    "sahel": "NER",  # Niger as Sahel proxy (WB data availability)
    "korea": "KOR",
    "syria": "SYR",
    "drc": "COD",
    "ethiopia": "ETH",
}

# Substring → ISO3 (longest match wins; list order not used — sorted by needle length at runtime)
_CONFLICT_SUBSTR_TO_WB_ISO3: List[tuple[str, str]] = [
    ("israel-palestine", "ISR"),
    ("taiwan-strait", "TWN"),
    ("north-korea", "PRK"),
    ("north korea", "PRK"),
    ("south-korea", "KOR"),
    ("south korea", "KOR"),
    ("us-iran", "IRN"),
    ("middle-east", "IRN"),
    ("hezbollah", "LBN"),
    ("houthi", "YEM"),
    ("palestine", "PSE"),
    ("israel", "ISR"),
    ("lebanon", "LBN"),
    ("ukraine", "UKR"),
    ("myanmar", "MMR"),
    ("ethiopia", "ETH"),
    ("dprk", "PRK"),
    ("syria", "SYR"),
    ("iran", "IRN"),
    ("yemen", "YEM"),
    ("sudan", "SDN"),
    ("taiwan", "TWN"),
    ("korea", "KOR"),
    ("sahel", "NER"),
    ("drc", "COD"),
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_conflict_slug(conflict: str) -> str:
    """Lowercase slug aligned with dashboard keys (e.g. 'US Iran' → 'us-iran')."""
    return (
        conflict.lower()
        .strip()
        .replace(" ", "-")
        .replace("_", "-")
    )


def _world_bank_country_for_conflict(conflict: str) -> Optional[str]:
    """Map conflict label to World Bank ISO3: exact slug first, then longest substring match."""
    if not conflict or not conflict.strip():
        return None
    key = _normalize_conflict_slug(conflict)
    if key in _EXACT_CONFLICT_TO_WB_ISO3:
        return _EXACT_CONFLICT_TO_WB_ISO3[key]
    for needle, iso in sorted(_CONFLICT_SUBSTR_TO_WB_ISO3, key=lambda x: -len(x[0])):
        if needle in key:
            return iso
    return None


async def _fetch_world_bank_country_indicators(wb_iso3: str) -> Dict[str, Any]:
    """Latest values for selected World Bank development indicators (open API, no key)."""
    if not wb_iso3:
        return {}
    out: Dict[str, Any] = {
        "country_iso3": wb_iso3.upper(),
        "source": "world_bank_open_data",
        "indicators": [],
    }
    iso = wb_iso3.upper()

    async def _one(
        client: httpx.AsyncClient, indicator_id: str, key: str, label: str
    ) -> Dict[str, Any]:
        try:
            resp = await client.get(
                f"{WORLD_BANK_BASE}/{iso}/indicator/{indicator_id}",
                params={"format": "json", "per_page": "1", "mrv": "1"},
            )
            if resp.status_code != 200:
                return {
                    "key": key,
                    "label": label,
                    "id": indicator_id,
                    "error": f"HTTP {resp.status_code}",
                }
            data = resp.json()
            if not isinstance(data, list) or len(data) < 2:
                return {"key": key, "label": label, "id": indicator_id, "error": "invalid response"}
            rows = data[1]
            if not isinstance(rows, list) or not rows:
                return {"key": key, "label": label, "id": indicator_id, "value": None, "date": None}
            row = rows[0]
            if not isinstance(row, dict):
                return {"key": key, "label": label, "id": indicator_id, "error": "bad row"}
            raw_val = row.get("value")
            num_val: Optional[float]
            if raw_val in (None, ""):
                num_val = None
            else:
                try:
                    num_val = float(raw_val)
                except (TypeError, ValueError):
                    num_val = None
            return {
                "key": key,
                "label": label,
                "id": indicator_id,
                "value": num_val,
                "date": row.get("date"),
            }
        except Exception as e:
            logger.debug("ENERGY: WB indicator %s failed: %s", indicator_id, e)
            return {"key": key, "label": label, "id": indicator_id, "error": str(e)}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            parts = await asyncio.gather(
                *(_one(client, iid, key, lbl) for iid, key, lbl in WB_MACRO_INDICATORS)
            )
            out["indicators"] = list(parts)
    except Exception as e:
        logger.debug("ENERGY: World Bank country indicators failed: %s", e)
        out["error"] = str(e)
    return out


async def _async_empty_wb() -> Dict[str, Any]:
    return {}


async def _fetch_fao_fpi() -> Dict[str, Any]:
    """Fetch FAO Food Price Index (monthly, free CSV)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(FAO_FPI_URL, follow_redirects=True)
            if resp.status_code != 200:
                if resp.status_code == 404:
                    logger.warning(
                        "ENERGY: FAO FPI URL returned 404 (file may have been moved). Set FAO_FPI_URL env to current CSV URL."
                    )
                return {"error": f"FAO FPI HTTP {resp.status_code}"}
            reader = csv.reader(io.StringIO(resp.text))
            rows = list(reader)
            if len(rows) < 3:
                return {"error": "FAO FPI: insufficient data"}
            header = [h.strip().lower() for h in rows[0]]
            # Find "food price index" or "date" columns
            date_col = next((i for i, h in enumerate(header) if "date" in h), 0)
            fpi_col = next(
                (i for i, h in enumerate(header) if "food" in h and "price" in h and "index" in h),
                next((i for i, h in enumerate(header) if "nominal" in h), 1),
            )
            latest = rows[-1]
            prev_year_row = rows[-13] if len(rows) > 13 else rows[1]
            index_val = _safe_float(latest[fpi_col]) if fpi_col < len(latest) else None
            prev_val = _safe_float(prev_year_row[fpi_col]) if fpi_col < len(prev_year_row) else None
            yoy = ((index_val - prev_val) / prev_val * 100) if index_val and prev_val and prev_val > 0 else None
            return {
                "index": index_val,
                "month": latest[date_col] if date_col < len(latest) else "",
                "yoy_change_pct": round(yoy, 1) if yoy is not None else None,
            }
    except Exception as e:
        logger.debug("ENERGY: FAO FPI fetch failed: %s", e)
        return {"error": str(e)}


async def _fetch_fertilizer_prices() -> Dict[str, Any]:
    """Fetch Urea/DAP prices from World Bank API (free, monthly)."""
    result: Dict[str, Any] = {"source": "world_bank"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for indicator, key in [(UREA_INDICATOR, "urea_price"), (DAP_INDICATOR, "dap_price")]:
                try:
                    resp = await client.get(
                        f"{WORLD_BANK_COMMODITIES_URL}/{indicator}",
                        params={"format": "json", "per_page": "2", "mrv": "1"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) and data[1]:
                            val = _safe_float(data[1][0].get("value"))
                            result[key] = val
                except Exception:
                    pass
    except Exception as e:
        logger.debug("ENERGY: fertilizer price fetch failed: %s", e)
        result["error"] = str(e)
    return result



def _commodity_entry(symbol: str, label: str, price: float, prev_price: float, as_of: str) -> Dict[str, Any]:
    """Build one commodity dict in the standard format."""
    change_pct = ((price - prev_price) / prev_price * 100) if prev_price and prev_price != 0 else None
    return {
        "symbol": symbol,
        "label": label,
        "price": f"{price:.2f}" if price else None,
        "change_pct": f"{change_pct:+.1f}%" if change_pct is not None else "0%",
        "change_pct_raw": change_pct,
        "as_of": as_of,
    }


async def _fetch_eia_oil_prices(api_key: str) -> List[Dict[str, Any]]:
    """Fetch oil (Brent, WTI) from EIA API v2 spot series. Returns empty list if no key or error."""
    if not api_key or not api_key.strip():
        return []
    results = []
    mapping = [(EIA_BRENT_SERIES, "BRENT", "Brent crude"), (EIA_WTI_SERIES, "WTI", "WTI crude")]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for series_id, symbol, label in mapping:
                try:
                    resp = await client.get(
                        f"{EIA_BASE}/{series_id}/data",
                        params={
                            "api_key": api_key.strip(),
                            "length": 5,
                            "sort[0][column]": "period",
                            "sort[0][direction]": "desc",
                        },
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    # EIA v2: response.data with period, value (strings)
                    records = (data.get("response") or {}).get("data") if isinstance(data, dict) else None
                    if not isinstance(records, list) or len(records) < 2:
                        continue
                    valid = [r for r in records if isinstance(r, dict) and r.get("value") not in (None, "", ".")]
                    if len(valid) < 2:
                        continue
                    latest, prev = valid[0], valid[1]
                    price = _safe_float(latest.get("value"), 0)
                    prev_p = _safe_float(prev.get("value"), 0)
                    if not price or not prev_p:
                        continue
                    period = latest.get("period") or latest.get("date") or ""
                    results.append(_commodity_entry(symbol, label, price, prev_p, period))
                except Exception as e:
                    logger.debug("ENERGY: EIA series %s failed: %s", series_id, e)
    except Exception as e:
        logger.debug("ENERGY: EIA oil fetch failed: %s", e)
    return results


async def _fetch_fred_oil_prices(api_key: str) -> List[Dict[str, Any]]:
    """Fetch oil (Brent, WTI) from FRED. Returns empty list if no key or error."""
    if not api_key or not api_key.strip():
        return []
    results = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for series_id, symbol, label in FRED_OIL_SERIES:
                try:
                    resp = await client.get(
                        FRED_BASE,
                        params={
                            "series_id": series_id,
                            "api_key": api_key.strip(),
                            "file_type": "json",
                            "sort_order": "desc",
                            "limit": 5,
                        },
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    obs = (data.get("observations") or []) if isinstance(data, dict) else []
                    valid = [o for o in obs if isinstance(o, dict) and o.get("value") not in (None, "", ".")]
                    if len(valid) < 2:
                        continue
                    latest, prev = valid[0], valid[1]
                    price = _safe_float(latest.get("value"), 0)
                    prev_p = _safe_float(prev.get("value"), 0)
                    if not price or not prev_p:
                        continue
                    as_of = latest.get("date") or ""
                    results.append(_commodity_entry(symbol, label, price, prev_p, as_of))
                except Exception as e:
                    logger.debug("ENERGY: FRED oil series %s failed: %s", series_id, e)
    except Exception as e:
        logger.debug("ENERGY: FRED oil fetch failed: %s", e)
    return results


async def _fetch_fred_food_prices(api_key: str) -> List[Dict[str, Any]]:
    """Fetch food (Wheat, Corn, Soybean) from FRED monthly series. Returns empty list if no key or error."""
    if not api_key or not api_key.strip():
        return []
    results = []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for series_id, symbol, label in FRED_FOOD_SERIES:
                try:
                    resp = await client.get(
                        FRED_BASE,
                        params={
                            "series_id": series_id,
                            "api_key": api_key.strip(),
                            "file_type": "json",
                            "sort_order": "desc",
                            "limit": 5,
                        },
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    obs = (data.get("observations") or []) if isinstance(data, dict) else []
                    valid = [o for o in obs if isinstance(o, dict) and o.get("value") not in (None, "", ".")]
                    if len(valid) < 2:
                        continue
                    latest, prev = valid[0], valid[1]
                    price = _safe_float(latest.get("value"), 0)
                    prev_p = _safe_float(prev.get("value"), 0)
                    if not price or not prev_p:
                        continue
                    as_of = latest.get("date") or ""
                    results.append(_commodity_entry(symbol, label, price, prev_p, as_of))
                except Exception as e:
                    logger.debug("ENERGY: FRED food series %s failed: %s", series_id, e)
    except Exception as e:
        logger.debug("ENERGY: FRED food fetch failed: %s", e)
    return results


async def _fetch_oil_prices(api_key: str) -> List[Dict[str, Any]]:
    """Fetch oil commodity quotes only (Brent, WTI) from Alpha Vantage."""
    return await _fetch_commodity_prices_for(api_key, OIL_SYMBOLS)


async def _fetch_food_prices(api_key: str) -> List[Dict[str, Any]]:
    """Fetch food commodity quotes (Wheat, Corn, Soybean)."""
    return await _fetch_commodity_prices_for(api_key, FOOD_SYMBOLS)


async def _fetch_commodity_prices_for(api_key: str, symbols: List[tuple]) -> List[Dict[str, Any]]:
    if not api_key:
        return []
    results = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for sym, label in symbols:
            try:
                resp = await client.get(
                    ALPHAVANTAGE_URL,
                    params={"function": sym, "interval": "daily", "apikey": api_key},
                )
                resp.raise_for_status()
                data = resp.json()
                series = data.get("data") or []
                if len(series) >= 2:
                    latest = series[0]
                    prev = series[1]
                    price = _safe_float(latest.get("value"))
                    prev_p = _safe_float(prev.get("value"))
                    change_pct = ((price - prev_p) / prev_p * 100) if prev_p and prev_p != 0 else None
                    results.append(
                        {
                            "symbol": sym,
                            "label": label,
                            "price": f"{price:.2f}" if price else None,
                            "change_pct": f"{change_pct:+.1f}%" if change_pct is not None else "0%",
                            "change_pct_raw": change_pct,
                            "as_of": latest.get("date", ""),
                        }
                    )
                else:
                    results.append({"symbol": sym, "label": label, "error": "Insufficient data"})
            except Exception as e:
                results.append({"symbol": sym, "label": label, "error": str(e)})
    return results


