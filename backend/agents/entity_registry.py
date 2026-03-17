"""
EntityRegistry – Centralized NER entity store per analysis run.

Replaces the ad-hoc ``exported_ner_entities`` with a dedicated, type-aware
entity structure supporting deduplication via alias matching and optional
embedding-based fuzzy matching.
"""

import logging
import threading
from typing import Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Alias lookup for known geopolitical actors.
# canonical_name -> [aliases]
ENTITY_ALIASES: Dict[str, List[str]] = {
    "IRGC": ["Islamic Revolutionary Guard Corps", "Sepah", "Pasdaran", "Iranian Revolutionary Guards"],
    "Hezbollah": ["Hizballah", "Hizbullah", "Hizb Allah"],
    "Hamas": ["Harakat al-Muqawama al-Islamiyya", "Islamic Resistance Movement"],
    "Houthis": ["Ansar Allah", "Ansarallah"],
    "IDF": ["Israel Defense Forces", "Tsahal", "Israeli military"],
    "CENTCOM": ["US Central Command", "United States Central Command"],
    "IAEA": ["International Atomic Energy Agency"],
    "OPCW": ["Organisation for the Prohibition of Chemical Weapons"],
    "Mossad": ["HaMossad leModiʿin uleTafkidim Meyuḥadim", "Institute for Intelligence"],
    "Quds Force": ["IRGC-QF", "Quds", "Jerusalem Force"],
    "PIJ": ["Palestinian Islamic Jihad", "Islamic Jihad"],
    "PMF": ["Popular Mobilization Forces", "Hashd al-Shaabi", "al-Hashd al-Shaabi"],
    "SDF": ["Syrian Democratic Forces"],
    "YPG": ["People's Protection Units"],
    "PKK": ["Kurdistan Workers' Party"],
    "AQAP": ["Al-Qaeda in the Arabian Peninsula"],
    "ISIS": ["ISIL", "IS", "Daesh", "Islamic State"],
}

# Inverted index: alias (lowered) -> canonical name
_ALIAS_INDEX: Dict[str, str] = {}
for canonical, aliases in ENTITY_ALIASES.items():
    _ALIAS_INDEX[canonical.lower()] = canonical
    for alias in aliases:
        _ALIAS_INDEX[alias.lower()] = canonical


class NEREntity(BaseModel):
    """A single named entity extracted from agent data."""

    entity: str
    type: str  # PERSON | ORG | LOCATION | VESSEL | WEAPON_SYSTEM
    source_agent: str
    confidence: float = 1.0
    context: Optional[str] = None


class EntityRegistry:
    """Central entity store for a single analysis run. Lives inside ResultStore."""

    def __init__(self) -> None:
        self._entities: List[NEREntity] = []
        self._lock = threading.Lock()

    def add(self, entity: NEREntity) -> None:
        with self._lock:
            self._entities.append(entity)

    def add_many(self, entities: List[NEREntity]) -> None:
        with self._lock:
            self._entities.extend(entities)

    def get_by_type(self, entity_type: str) -> List[NEREntity]:
        with self._lock:
            return [e for e in self._entities if e.type == entity_type]

    def get_all(self) -> List[NEREntity]:
        with self._lock:
            return list(self._entities)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._entities)

    def deduplicate(self) -> None:
        """Merge duplicate entities using alias matching.

        Phase 1: Alias-based merge using the ENTITY_ALIASES lookup table.
        Phase 2 (future): Embedding-based fuzzy matching for unknown entities.
        """
        with self._lock:
            self._alias_merge()

    def _alias_merge(self) -> None:
        """Replace known aliases with canonical names and merge duplicates."""
        seen: Dict[str, NEREntity] = {}  # (canonical_lower, type) -> entity
        merged: List[NEREntity] = []

        for ent in self._entities:
            canonical = _ALIAS_INDEX.get(ent.entity.lower(), ent.entity)
            key = f"{canonical.lower()}|{ent.type}"
            if key in seen:
                existing = seen[key]
                if ent.confidence > existing.confidence:
                    existing.confidence = ent.confidence
                if ent.context and not existing.context:
                    existing.context = ent.context
            else:
                normalized = NEREntity(
                    entity=canonical,
                    type=ent.type,
                    source_agent=ent.source_agent,
                    confidence=ent.confidence,
                    context=ent.context,
                )
                seen[key] = normalized
                merged.append(normalized)

        self._entities = merged

    def to_list(self) -> List[Dict]:
        """Serialize all entities to list of dicts (for JSON output)."""
        with self._lock:
            return [e.model_dump() for e in self._entities]
