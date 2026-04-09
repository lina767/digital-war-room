import csv
import io
import logging
import re
import time
from typing import Any, Dict, List

import httpx

from ..utils import run_async
from services.http_client import get_http_client

logger = logging.getLogger(__name__)

_HTTP_HEADERS = {"User-Agent": "DigitalWarRoom/1.0 (compliance-monitoring)", "Accept": "*/*"}

OFAC_SDN_CSV_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
EU_SANCTIONS_CSV_URL = (
    "https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw"
)
EU_SANCTIONS_XML_URL = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xml/fullSanctionsList_1_1.xml"
UN_PRESS_RSS = "https://press.un.org/en/rss/press.xml"
UN_NEWS_RSS = "https://news.un.org/feed/subscribe/en/news/all/rss.xml"
ICJ_RSS = "https://www.icj-cij.org/rss/en-press-releases.xml"

CONFLICT_SANCTION_KEYWORDS: Dict[str, List[str]] = {
    "iran": ["iran", "irgc", "iranian", "tehran", "qods", "khamenei"],
    "us-iran": ["iran", "irgc", "iranian", "tehran"],
    "russia": ["russia", "russian", "ukraine", "donbas", "crimea", "putin"],
    "ukraine": ["ukraine", "russia", "donbas", "crimea"],
    "syria": ["syria", "syrian", "assad"],
    "north korea": ["dprk", "north korea", "kim jong"],
    "middle east": ["iran", "irgc", "syria", "syrian", "hezbollah", "lebanon", "yemen", "houthi", "iraq", "israel", "gaza", "ofac", "sanctions"],
    "naher osten": ["iran", "irgc", "syria", "syrian", "hezbollah", "lebanon", "yemen", "houthi", "iraq", "israel", "gaza", "ofac", "sanctions"],
    "hezbollah": ["hezbollah", "lebanon", "nasrallah", "ofac", "sanctions", "iran", "irgc", "qods"],
    "houthis": ["houthi", "houthis", "yemen", "ansar allah", "ofac", "sanctions", "iran", "red sea"],
    "default": ["iran", "russia", "syria"],
}

_ofac_cache: Dict[str, Any] = {"text": None, "ts": 0.0}
_OFAC_CACHE_TTL = 6 * 3600
_eu_cache: Dict[str, Any] = {"text": None, "ts": 0.0}
_EU_CACHE_TTL = 6 * 3600


def _conflict_to_keywords(conflict: str) -> List[str]:
    cl = (conflict or "").lower()
    for k, v in CONFLICT_SANCTION_KEYWORDS.items():
        if k != "default" and k in cl:
            return v
    return CONFLICT_SANCTION_KEYWORDS["default"]


async def _stream_download(url: str, connect_s: float = 15, read_s: float = 90) -> str:
    del connect_s  # shared client uses one timeout value per request
    client = get_http_client()
    resp = await client.request(
        "GET",
        url,
        timeout=read_s,
        retries=2,
        follow_redirects=True,
        headers=_HTTP_HEADERS,
        service_name="diplo_download",
    )
    return resp.text


async def fetch_ofac_sdn(conflict: str) -> Dict[str, Any]:
    keywords = _conflict_to_keywords(conflict)
    try:
        now = time.time()
        if _ofac_cache["text"] and (now - _ofac_cache["ts"]) < _OFAC_CACHE_TTL:
            text = _ofac_cache["text"]
        else:
            text = await _stream_download(OFAC_SDN_CSV_URL, connect_s=15, read_s=120)
            _ofac_cache["text"] = text
            _ofac_cache["ts"] = now

        reader = csv.reader(io.StringIO(text))
        matches: List[Dict[str, Any]] = []
        programs_seen: Dict[str, int] = {}
        for row in reader:
            if len(row) < 4:
                continue
            name = (row[1] or "").strip().lower()
            program = (row[3] or "").strip().lower()
            combined = name + " " + program
            if any(k in combined for k in keywords):
                prog_raw = (row[3] or "").strip()
                matches.append({"name": row[1].strip(), "type": row[2].strip() if len(row) > 2 else "", "program": prog_raw})
                for p in prog_raw.replace(";", " ").replace(",", " ").split():
                    p = p.strip(" '\"[]")
                    if p and len(p) > 1:
                        programs_seen[p] = programs_seen.get(p, 0) + 1
        top_programs = sorted(programs_seen.items(), key=lambda x: -x[1])[:10]
        return {
            "total_matches": len(matches),
            "sample": matches[:20],
            "programs": [{"name": p, "count": c} for p, c in top_programs],
            "error": None,
        }
    except Exception as e:
        logger.warning("OFAC SDN fetch failed: %s", e)
        return {"total_matches": 0, "sample": [], "programs": [], "error": str(e)}


async def fetch_eu_sanctions(conflict: str) -> Dict[str, Any]:
    keywords = _conflict_to_keywords(conflict)
    try:
        now = time.time()
        if _eu_cache["text"] and (now - _eu_cache["ts"]) < _EU_CACHE_TTL:
            text = _eu_cache["text"]
        else:
            try:
                text = await _stream_download(EU_SANCTIONS_CSV_URL, connect_s=15, read_s=60)
            except Exception:
                text = await _stream_download(EU_SANCTIONS_XML_URL, connect_s=15, read_s=90)
            _eu_cache["text"] = text
            _eu_cache["ts"] = now

        count = 0
        for k in keywords:
            count += len(re.findall(re.escape(k), text, re.I))
        return {"keyword_mentions": count, "error": None}
    except Exception as e:
        logger.warning("EU sanctions fetch failed: %s", e)
        return {"keyword_mentions": 0, "error": str(e)}


async def _fetch_diplo_rss(url: str, label: str, conflict: str) -> List[Dict[str, Any]]:
    import feedparser

    keywords = _conflict_to_keywords(conflict)
    try:
        client = get_http_client()
        resp = await client.request(
            "GET",
            url,
            timeout=15.0,
            retries=2,
            headers=_HTTP_HEADERS,
            service_name="diplo_rss",
        )
        feed = feedparser.parse(resp.text)
        entries = []
        for e in getattr(feed, "entries", [])[:20]:
            title = (e.get("title") or "").strip()
            summary = (e.get("summary") or e.get("description") or "")[:400]
            if not keywords or any(k in (title + summary).lower() for k in keywords):
                entries.append(
                    {
                        "title": title,
                        "url": e.get("link"),
                        "published": e.get("published"),
                        "source": label,
                        "summary": summary,
                    }
                )
        return entries
    except httpx.HTTPStatusError as e:
        return [{"title": f"{label} error", "error": f"HTTP {e.response.status_code}"}]
    except Exception as e:
        return [{"title": f"{label} error", "error": str(e)}]


_DIPLO_KEYWORD_MAP = {
    "new_sanction": ["sanction", "designat", "blacklist", "restrict", "penalt", "asset freeze"],
    "enforcement": ["enforce", "comply", "violat", "seiz", "intercept", "impound"],
    "statement": ["statement", "condemn", "urge", "call on", "express concern", "deplore"],
    "legal_proceeding": ["resolution", "court", "ruling", "judgment", "tribunal", "icj", "icc"],
    "humanitarian": ["humanitarian", "civilian", "refugee", "displaced", "aid", "relief"],
}


def _classify_diplo_rule_based(text: str) -> Dict[str, Any]:
    """Keyword-based diplo classification (replaces Haiku batch_classify_diplo)."""
    text_lower = text.lower()
    for category, keywords in _DIPLO_KEYWORD_MAP.items():
        if any(kw in text_lower for kw in keywords):
            return {"category": category, "confidence": 0.7}
    return {"category": "other", "confidence": 0.5}


def _classify_un_icj_news(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return items

    try:
        from services.haiku_service import batch_classify_diplo

        texts = [((e.get("title") or "") + " " + (e.get("summary") or "")).strip()[:1500] for e in items]
        results = run_async(batch_classify_diplo(texts))
        if not results or all(r is None for r in results):
            return items
        out = []
        for e, res in zip(items, results, strict=True):
            if res and isinstance(res, dict):
                e["diplo_category"] = res.get("category", "irrelevant")
                e["diplo_confidence"] = float(res.get("confidence", 0))
                if e["diplo_category"] == "irrelevant" and e["diplo_confidence"] >= 0.7:
                    continue
            out.append(e)
        return out if out else items
    except Exception:
        return items


async def fetch_un_icj_news(conflict: str) -> List[Dict[str, Any]]:
    un_entries = await _fetch_diplo_rss(UN_PRESS_RSS, "UN", conflict)
    if un_entries and len(un_entries) == 1 and un_entries[0].get("error"):
        un_entries = await _fetch_diplo_rss(UN_NEWS_RSS, "UN News", conflict)
    icj_entries = await _fetch_diplo_rss(ICJ_RSS, "ICJ", conflict)
    combined = (un_entries or [])[:10] + (icj_entries or [])[:10]
    items = [e for e in combined if isinstance(e, dict) and "error" not in e][:15]
    return _classify_un_icj_news(items)
