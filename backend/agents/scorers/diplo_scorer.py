from typing import Any, Dict, List


def compute_diplo_score(ofac: Dict[str, Any], eu: Dict[str, Any], news: List[Dict[str, Any]]) -> float:
    """Score 0-100: more sanctions matches and UN/ICJ coverage = higher diplomatic tension."""
    base = 28.0
    ofac_count = int(ofac.get("total_matches") or 0)
    if ofac_count > 500:
        base += 22
    elif ofac_count > 200:
        base += 15
    elif ofac_count > 50:
        base += 10
    elif ofac_count > 0:
        base += 5

    eu_mentions = int(eu.get("keyword_mentions") or 0)
    if eu_mentions > 1000:
        base += 15
    elif eu_mentions > 100:
        base += 8

    valid_news = [n for n in news if n.get("title") and "error" not in n]
    if len(valid_news) >= 5:
        base += 20
    elif len(valid_news) >= 2:
        base += 10
    elif len(valid_news) >= 1:
        base += 5

    if any(
        n.get("diplo_category") == "new_sanction" and float(n.get("diplo_confidence") or 0) >= 0.6 for n in valid_news
    ):
        base += 5

    return min(100.0, max(0.0, base))
