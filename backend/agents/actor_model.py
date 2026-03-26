"""
Actor model for conflict synthesis: builds actor lists with activity scores from key_findings.
Supports Iran/Levant, Red Sea/Horn, Ukraine and Taiwan theaters.
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

LEBANON_THEATER_ACTORS = [
    {"id": "lebanon", "name": "Lebanon", "role": "defender"},
    {"id": "hezbollah", "name": "Hezbollah", "role": "retaliating"},
    {"id": "israel", "name": "Israel", "role": "aggressor"},
    {"id": "syria", "name": "Syria", "role": "neutral"},
    {"id": "iran", "name": "Iran", "role": "retaliating"},
    {"id": "united_states", "name": "United States", "role": "aggressor"},
    {"id": "unifil", "name": "UNIFIL", "role": "defender"},
]

RED_SEA_HORN_ACTORS = [
    {"id": "houthis", "name": "Houthis", "role": "retaliating"},
    {"id": "yemen", "name": "Yemen", "role": "neutral"},
    {"id": "somalia", "name": "Somalia", "role": "neutral"},
    {"id": "ethiopia", "name": "Ethiopia", "role": "neutral"},
    {"id": "eritrea", "name": "Eritrea", "role": "neutral"},
    {"id": "djibouti", "name": "Djibouti", "role": "defender"},
    {"id": "us_naval_presence", "name": "US Naval Presence", "role": "defender"},
    {"id": "eu_naval_presence", "name": "EU Naval Presence", "role": "defender"},
]

UKRAINE_THEATER_ACTORS = [
    {"id": "ukraine", "name": "Ukraine", "role": "defender"},
    {"id": "russia", "name": "Russia", "role": "aggressor"},
    {"id": "nato", "name": "NATO", "role": "defender"},
    {"id": "european_union", "name": "European Union", "role": "defender"},
    {"id": "belarus", "name": "Belarus", "role": "neutral"},
    {"id": "black_sea_fleet", "name": "Black Sea Fleet", "role": "aggressor"},
]

TAIWAN_STRAIT_ACTORS = [
    {"id": "taiwan", "name": "Taiwan", "role": "defender"},
    {"id": "china", "name": "China", "role": "aggressor"},
    {"id": "united_states", "name": "United States", "role": "defender"},
    {"id": "japan", "name": "Japan", "role": "defender"},
    {"id": "philippines", "name": "Philippines", "role": "neutral"},
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
    """Build actors list for the conflict with activity from key_findings."""
    if not conflict:
        return []
    conflict_lc = conflict.lower()
    if "lebanon" in conflict_lc or "hezbollah" in conflict_lc:
        actors = LEBANON_THEATER_ACTORS
    elif any(k in conflict_lc for k in ["red sea", "horn", "bab", "mandeb", "houthi"]):
        actors = RED_SEA_HORN_ACTORS
    elif any(k in conflict_lc for k in ["ukraine", "russia", "black sea"]):
        actors = UKRAINE_THEATER_ACTORS
    elif any(k in conflict_lc for k in ["taiwan", "south china sea"]):
        actors = TAIWAN_STRAIT_ACTORS
    elif "iran" in conflict_lc:
        actors = IRAN_ACTORS
    else:
        return []
    out = []
    for a in actors:
        activity = actor_activity_from_findings(a["id"], a["name"], key_findings)
        out.append(
            {
                "id": a["id"],
                "name": a["name"],
                "role": a["role"],
                "activity": activity,
            }
        )
    return out
