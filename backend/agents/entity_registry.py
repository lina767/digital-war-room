"""
EntityRegistry – Centralized NER entity store per analysis run.

Replaces the ad-hoc ``exported_ner_entities`` with a dedicated, type-aware
entity structure supporting deduplication via alias matching and optional
embedding-based fuzzy matching.
"""

import logging
import os
import threading
from typing import Dict, List, Optional, Tuple

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


def _cosine_name_sim(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return inter / max(len(sa), len(sb))


class NEREntity(BaseModel):
    """A single named entity extracted from agent data."""

    entity: str
    type: str  # PERSON | ORG | LOCATION | VESSEL | WEAPON_SYSTEM
    source_agent: str
    confidence: float = 1.0
    context: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


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
        Phase 2: Embedding-based fuzzy merge when HUGGINGFACE_API_KEY is set.
        """
        with self._lock:
            self._alias_merge()
            self._embedding_merge()
            self._geo_cluster_locations()

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
                    lat=ent.lat,
                    lon=ent.lon,
                )
                seen[key] = normalized
                merged.append(normalized)

        self._entities = merged

    def _embedding_merge(self) -> None:
        """Merge near-duplicate entity strings within each type (HF embeddings)."""
        if not os.getenv("HUGGINGFACE_API_KEY", "").strip():
            return
        if len(self._entities) < 2:
            return
        try:
            from agents.utils import run_async
            from services.hf_service import _cosine_similarity, embed
        except Exception as e:
            logger.debug("entity embedding merge skipped: %s", e)
            return

        threshold = float(os.getenv("ENTITY_EMBED_MERGE_THRESHOLD", "0.88"))
        by_type: Dict[str, List[Tuple[int, NEREntity]]] = {}
        for i, e in enumerate(self._entities):
            by_type.setdefault(e.type, []).append((i, e))

        merge_map: Dict[int, int] = {}  # i -> representative index

        for _, members in by_type.items():
            if len(members) < 2:
                continue
            texts = [m[1].entity[:512] for m in members]
            vectors = run_async(embed(texts))
            if not vectors or len(vectors) != len(members):
                continue
            n = len(members)
            uf = list(range(n))

            def find(x: int) -> int:
                while uf[x] != x:
                    uf[x] = uf[uf[x]]
                    x = uf[x]
                return x

            def union(a: int, b: int) -> None:
                ra, rb = find(a), find(b)
                if ra != rb:
                    uf[rb] = ra

            for i in range(n):
                for j in range(i + 1, n):
                    if _cosine_similarity(vectors[i], vectors[j]) >= threshold:
                        union(i, j)

            groups: Dict[int, List[int]] = {}
            for i in range(n):
                r = find(i)
                groups.setdefault(r, []).append(i)

            for idxs in groups.values():
                if len(idxs) < 2:
                    continue
                ents = [members[k][1] for k in idxs]
                best = max(ents, key=lambda x: (x.confidence, len(x.entity)))
                rep_global = members[idxs[0]][0]
                for k in idxs[1:]:
                    merge_map[members[k][0]] = rep_global
                self._entities[rep_global] = NEREntity(
                    entity=best.entity,
                    type=best.type,
                    source_agent=",".join(sorted({e.source_agent for e in ents})),
                    confidence=max(e.confidence for e in ents),
                    context=next((e.context for e in ents if e.context), None),
                    lat=next((e.lat for e in ents if e.lat is not None), None),
                    lon=next((e.lon for e in ents if e.lon is not None), None),
                )

        if not merge_map:
            return
        new_list: List[NEREntity] = []
        dropped = set(merge_map.keys())
        for i, ent in enumerate(self._entities):
            if i in dropped:
                continue
            new_list.append(ent)
        self._entities = new_list

    def _geo_cluster_locations(self) -> None:
        """Merge LOCATION entities within ~80 km when lat/lon are present."""
        km_max = float(os.getenv("ENTITY_LOCATION_MERGE_KM", "80"))
        locs = [i for i, e in enumerate(self._entities) if e.type == "LOCATION" and e.lat is not None and e.lon is not None]
        if len(locs) < 2:
            return

        def dist_km(a: NEREntity, b: NEREntity) -> float:
            from math import asin, cos, radians, sin, sqrt

            r = 6371.0
            la1, lo1, la2, lo2 = map(radians, [a.lat, a.lon, b.lat, b.lon])
            dlat, dlon = la2 - la1, lo2 - lo1
            h = sin(dlat / 2) ** 2 + cos(la1) * cos(la2) * sin(dlon / 2) ** 2
            return 2 * r * asin(min(1.0, sqrt(h)))

        merge_into: Dict[int, int] = {}
        for ii in range(len(locs)):
            i = locs[ii]
            if i in merge_into:
                continue
            for jj in range(ii + 1, len(locs)):
                j = locs[jj]
                if j in merge_into:
                    continue
                ei, ej = self._entities[i], self._entities[j]
                if dist_km(ei, ej) <= km_max and ei.entity.lower() != ej.entity.lower():
                    # Only merge if names are somewhat similar or one contains the other
                    a, b = ei.entity.lower(), ej.entity.lower()
                    if a in b or b in a or _cosine_name_sim(a, b) >= 0.5:
                        merge_into[j] = i

        if not merge_into:
            return

        for j, i in merge_into.items():
            ei, ej = self._entities[i], self._entities[j]
            keep = ei if ei.confidence >= ej.confidence else ej
            other = ej if keep is ei else ei
            self._entities[i] = NEREntity(
                entity=keep.entity,
                type="LOCATION",
                source_agent=",".join(sorted({keep.source_agent, other.source_agent})),
                confidence=max(ei.confidence, ej.confidence),
                context=keep.context or other.context,
                lat=keep.lat,
                lon=keep.lon,
            )

        self._entities = [e for k, e in enumerate(self._entities) if k not in merge_into]

    def to_list(self) -> List[Dict]:
        """Serialize all entities to list of dicts (for JSON output)."""
        with self._lock:
            return [e.model_dump() for e in self._entities]
