"""
Actor model for conflict synthesis: builds actor lists with activity scores from key_findings.
Currently Iran-specific; structured for future conflict-specific config.
"""
from typing import Any, Dict, List

# Iran conflict actors (aligned with conflicts.app). Activity derived from key_findings mentions.
IRAN_ACTORS = [
    {"id": "israel", "name": "Israel", "role": "aggressor"},
    {"id": "united_states", "name": "United States", "role": "aggressor"},
    {"id": "iran", "name": "Iran", "role": "retaliating"},
    {"id": "irgc", "name": "IRGC", "role": "retaliating"},
    {"id": "nato", "name": "NATO", "role": "defender"},
    {"id": "hezbollah", "name": "Hezbollah", "role": "retaliating"},
    {"id": "us_il_joint", "name": "US–IL Joint", "role": "aggressor"},
    {"id": "russia", "name": "Russia", "role": "neutral"},
    {"id": "houthis", "name": "Houthis", "role": "retaliating"},
    {"id": "iraqi_pmf", "name": "Iraqi PMF", "role": "neutral"},
]


def actor_activity_from_findings(actor_id: str, actor_name: str, key_findings: List[str]) -> int:
    """Compute activity 0–100 from key_findings mention count."""
    text = " ".join(key_findings).lower()
    terms = []
    if actor_id == "us_il_joint":
        terms = ["us", "israel", "joint", "strike"]
    elif actor_id == "irgc":
        terms = ["irgc", "revolutionary guard"]
    elif actor_id == "iraqi_pmf":
        terms = ["pmf", "iraqi", "popular mobilization"]
    else:
        terms = [actor_name.lower(), actor_id.replace("_", " ")]
    count = sum(1 for t in terms if t in text)
    if count == 0:
        return 40
    return min(100, 40 + count * 15)


def build_actors_for_conflict(conflict: str, key_findings: List[str]) -> List[Dict[str, Any]]:
    """Build actors list for the conflict with activity from key_findings. Iran only for now."""
    if not conflict or "iran" not in conflict.lower():
        return []
    out = []
    for a in IRAN_ACTORS:
        activity = actor_activity_from_findings(a["id"], a["name"], key_findings)
        out.append({
            "id": a["id"],
            "name": a["name"],
            "role": a["role"],
            "activity": activity,
        })
    return out
