# Umsetzung Haiku + Hugging Face im Digital War Room (überarbeitet)

**Aktueller Umsetzungsbereich:** Es werden nur **Phase 1 bis Phase 4** umgesetzt. **Phase 5 (Bild-Ingest, OCR, CLIP)** und **Phase 6 (Object Detection)** werden vorerst **nicht** umgesetzt und bleiben für später eingeplant. Phasenweise Ausführung: je eine Agent-Session pro Phase; nur **Session 1 (Phase 1)** bis **Session 4 (Phase 4)** durchführen.

### So startest du die Umsetzung (Cursor)

Pro Phase eine **neue Chat-Session** öffnen und genau eine Phase ausführen lassen, damit der Kontext kurz bleibt.

| Session | In der neuen Session sagen / eingeben |
|--------|---------------------------------------|
| **Phase 1** | „Phase 1 aus diesem Plan umsetzen.“ oder „Setze nur Phase 1 aus docs/PLAN-Haiku-HF-Implementation.md um.“ |
| **Phase 2** | „Phase 2 aus diesem Plan umsetzen.“ oder „Setze nur Phase 2 aus docs/PLAN-Haiku-HF-Implementation.md um.“ |
| **Phase 3** | „Phase 3 aus diesem Plan umsetzen.“ oder „Setze nur Phase 3 aus docs/PLAN-Haiku-HF-Implementation.md um.“ |
| **Phase 4** | „Phase 4 aus diesem Plan umsetzen.“ oder „Setze nur Phase 4 aus docs/PLAN-Haiku-HF-Implementation.md um.“ |

Diesen Plan (oder die Datei `docs/PLAN-Haiku-HF-Implementation.md`) in der Session referenzieren (z. B. mit @), dann Build/Agent starten. Der Agent soll in dieser Session **nur** die genannte Phase umsetzen und keine anderen Phasen anfassen.

## Ausgangslage im Projekt

- **Pipeline:** `run_periodic_analysis()` in [backend/main.py](backend/main.py) ruft alle 6h `analyze_conflict(AUTO_ANALYZE_CONFLICT)` auf. `analyze_conflict` in [backend/agents/supervisor.py](backend/agents/supervisor.py) führt `_collect_all_agents(conflict)` (12 Agents parallel via `ThreadPoolExecutor`) und danach `_synthesize()` aus. Es gibt **keine** zentrale sequenzielle Pipeline; die Reihenfolge aus dem Plan muss **pro Agent** bzw. in den neuen Services abgebildet werden.
- **Sync/Async:** Alle Agent-Einstiege sind synchron. Es existiert [backend/agents/utils.py](backend/agents/utils.py) mit `run_async(coro)`. Haiku- und HF-Services **async**; Aufrufe aus Agents über `run_async(...)`.
- **Bestehende Treffer:** NEWS (`_merge_news_results`, `_run_news_fusion_agent`), SOCMINT (`_run_rule_based_socmint`, `_sentiment`), Signal Framework (`_ensure_english_display`, `_is_mostly_farsi`), FININT (OFAC), GEOINT (Regionen/FIRMS), Supervisor (`_compact_for_llm`, `_synthesize`).
- **Infrastruktur:** Kein pgvector/DATABASE_URL im Repo. Phase 3 erfordert Railway PostgreSQL + Migration. **Kein numpy** in Phase 1–2 (siehe unten).

---

## Architektur-Entscheidung: Wo läuft was?

- **Translation:** In den Agents mit Farsi-Content (Signal Framework, NEWS für Farsi-RSS).
- **Embedding-Dedup + Cross-Encoder-Ranking:** In NEWS **innerhalb** `_merge_news_results` (nach URL-Dedup, **vor** Scoring/Cutoff). In SOCMINT in `_run_rule_based_socmint` nach dem Sammeln von `all_posts`.
- **Classification / NER / Sentiment:** Sentiment und NER in den Agents (NEWS, SOCMINT). **NER-Anreicherung für FININT/GEOINT:** über einen **Post-Processing-Schritt im Supervisor** nach `_collect_all_agents`, vor `_synthesize`: NER-Ergebnisse aus NEWS/SOCMINT werden an FININT/GEOINT weitergegeben, deren Reports nachträglich angereichert (OFAC-Matching auf NER-Entitäten, Location-Verknüpfung). Kein paralleles „Übergeben“ — die Agents laufen weiter parallel; der Supervisor führt einen zweiten, kurzen Durchlauf durch, der nur NER → FININT/GEOINT-Anreicherung macht.
- **Error-Recovery:** Bei Haiku-Fehler (Rate Limit, Timeout) **gesamten Batch** auf Fallback umschalten (regelbasiert oder HF-Bulk), nicht nur den einzelnen Call mit `None`. So bleibt der Datensatz für den Supervisor konsistent (kein Mix aus „einige Items mit NER, andere ohne“).

---

## Phase 1 — Haiku-Agent-Layer + HF Embeddings + Cross-Encoder

### 1.1 Neue Dateien

| Datei | Inhalt |
|-------|--------|
| **backend/services/haiku_service.py** | Anthropic-Client, Call-Counter, **Budget-Tracker auf Basis der API-Response:** pro Haiku-Call `usage = response.usage` auslesen und `input_tokens`/`output_tokens` in einen monatlichen Zähler schreiben (keine Schätzung). Zweizeiler pro Call: z. B. `_increment_usage(usage.input_tokens, usage.output_tokens)`; Warnung bei 80 % Monatsbudget. Nur `translate_fa_en()` für Phase 1; Graceful Degradation (try/except → Fallback/None). |
| **backend/services/hf_service.py** | `httpx.AsyncClient`, Auth, In-Memory-Cache mit TTL. **Cosine-Similarity ohne numpy:** reines Python mit `sum(a*b for a,b in zip(v1,v2))` und `math.sqrt(sum(x*x for x in v1))` (5-Zeilen-Snippet für 384-dim Vektoren). Alternativ `scipy.spatial.distance.cosine`, falls scipy bereits transitiv vorhanden. **Cold Start / Health-Check:** Am Anfang jedes 6h-Laufs einen **Warmup-Call** für die genutzten HF-Endpoints (z. B. einmal `embed(["warmup"])` und ggf. Cross-Encoder mit einem Dummy-Paar), damit der erste „echte“ Call nicht 20–60 s blockiert. **Timeout** für HF-Calls großzügig setzen (z. B. 30–60 s), da kleine HF-Modelle beim ersten Request oft cold sind. |

### 1.2 Embedding-Dedup und Cross-Encoder in NEWS (in _merge_news_results)

- **Stelle:** [backend/agents/news_agent.py](backend/agents/news_agent.py) — **Funktion `_merge_news_results` selbst anpassen**, nicht der Code danach in `_run_news_fusion_agent`.
- **Ablauf in `_merge_news_results`:**
  1. URL-Dedup wie bisher → `articles = list(seen.values())`.
  2. **Neu:** Embedding-Dedup auf `articles` (über `run_async(hf_service.deduplicate_items(articles, text_key="title", threshold=0.92))`); Ergebnis wieder `articles`. So werden Duplikate **vor** dem Cutoff entfernt; es gehen keine relevanten Artikel verloren, die ein Duplikat verdrängt hätte.
  3. **Neu:** Cross-Encoder-Ranking. Query **nicht** fest als `f"{conflict} nuclear sanctions military"` — das ist für Konflikte wie „Myanmar civil war“ unsinnig. Stattdessen: **entweder** eine konfigurierbare **RANKING_QUERY** pro Konflikt-Profil (z. B. Env oder Config: `RANKING_QUERY_IRAN="Iran nuclear sanctions military"`, `RANKING_QUERY_MYANMAR="Myanmar civil war military junta"`), **oder** die Query dynamisch aus den Top-Keywords des Laufs ableiten (z. B. häufigste NER-Entitäten aus vorherigen Läufen aus DB/Cache). Konkret im Plan: Konfiguration pro Konflikt (z. B. Dict/Env mit Fallback auf `conflict`-String) dokumentieren; dynamische Ableitung aus NER kann Phase 2+ sein.
  4. Mit der gewählten Query: `ranked = run_async(rank_by_relevance(query, texts, top_k=20))`, dann `articles = [articles[i] for i, _ in ranked]` → das sind die Top-20 nach Relevanz.
  5. **Weiter wie bisher:** weighted sentiment, source_breakdown, `top20 = articles` (bereits 20), return.

- **Signatur:** `_merge_news_results` muss dafür einen zusätzlichen Parameter erhalten (z. B. `conflict: str | None = None` oder `ranking_query: str | None = None`), damit die Fusion-Agent-Stufe die Query übergeben kann. Wenn `ranking_query` fehlt, Fallback: nur nach Sentiment sortieren wie bisher (kein Cross-Encoder).

### 1.3 Translation einbauen

- **Signal Framework:** In `_ensure_english_display` bei Farsi-Content: `exile_en = run_async(translate_fa_en(exile_raw))`; bei `None` Platzhalter beibehalten.
- **NEWS:** Bei Farsi-RSS-Einträgen Titel/Summary für Display optional per `translate_fa_en`; Sentiment auf Originaltext.

### 1.4 SOCMINT

- In `_run_rule_based_socmint` nach `all_posts = telegram + ...`: `all_posts = run_async(deduplicate_items(all_posts, text_key="text", threshold=0.92))`; Rest unverändert.

### 1.5 Konfiguration

- Env: `HUGGINGFACE_API_KEY`, `HAIKU_MODEL`, `HAIKU_MAX_*`, `HAIKU_MONTHLY_BUDGET`, `HF_CACHE_MAX_SIZE`, **HF_API_TIMEOUT** (z. B. 45 oder 60 für Cold Start). Optional pro Konflikt: `RANKING_QUERY_IRAN`, `RANKING_QUERY_<KONFLIKT>`.
- **Kein numpy** in requirements für Phase 1–2; erst Phase 3 (pgvector) übernimmt Similarity in der DB.

---

## Phase 2 — Haiku Sentiment + NER (+ HF-NER-Fallback)

- **haiku_service.py:** `sentiment()`, `ner()`, Batch-Varianten; **Budget-Tracker:** weiterhin echte `usage.input_tokens` / `usage.output_tokens` pro Call.
- **Error-Recovery:** Wenn ein Haiku-Call (z. B. NER) fehlschlägt, **gesamten Batch** auf Fallback umschalten (regelbasierte Sentiment-Logik, HF-Bulk-NER), damit der Supervisor keinen inkonsistenten Mix aus „teilweise NER, teilweise None“ bekommt.
- **NER-Pipeline:** Haiku primär, HF-Bulk für Overflow; Ergebnisse in NEWS/SOCMINT-Output als `entities`.
- **Weitergabe NER → FININT/GEOINT:** **Entschieden:** Ein **Post-Processing-Schritt im Supervisor** nach `_collect_all_agents`, vor `_synthesize`:
  1. Aus `agent_results["news"]` und `agent_results["socmint"]` die NER-Ergebnisse (`entities`) auslesen.
  2. FININT: OFAC-Matching auf die extrahierten PERSON/ORG-Entitäten (zusätzlich zu bestehender Keyword-Logik); Report anreichern.
  3. GEOINT: LOCATION-Entitäten mit Anomalie-Regionen verknüpfen; Report anreichern.
  4. Angereicherte FININT/GEOINT-Daten gehen in die gleiche `agent_results`-Struktur (oder ein erweitertes Payload) für `_synthesize`.

  So laufen alle Agents weiter parallel; nur der Supervisor macht einen kurzen zweiten Durchlauf ohne erneuten Agent-Run.

---

## Phase 3 — Zero-Shot Pre-Filter + Summarization + pgvector

- Supervisor: Optional Pre-Filter vor `_compact_for_llm` (Classification, „other“/low confidence rausfiltern); optional Summarization für lange Texte.
- pgvector: Migration, `storage_service`; Similarity dann in der DB — numpy/Python-Cosine nur noch für In-Memory-Cache optional.

---

## Phase 4 — Document QA (PDF-Quellen)

- `hf_service.document_qa`; PDF-Ingest; FININT-Integration (Fragen zu Entitäten über OFAC/UN-PDF-Chunks).

---

## Phase 5 — Bild-Ingest + OCR + CLIP (noch nicht umsetzen)

**Status:** Vorerst zurückgestellt. Erst wenn Phase 1–4 stehen, bei Bedarf umsetzen.

**Ab hier HF Pro ($9/Monat) aktivieren.** CV-Modelle (OCR, CLIP, Deepfake) sind GPU-intensiv; der Free Tier reicht für den Bild-Ingest-Betrieb in der Regel nicht. Klare Entscheidungslinie: Phase 1–4 mit HF Free; ab Phase 5 HF Pro.

- **Telegram als eigener Ingest-Pfad:** Telegram-Bilder kommen über die **Bot-API als `file_id`**, nicht als URL. Pfad: `getFile` aufrufen → temporäre Download-URL erhalten (läuft nach ca. 1 h ab) → Inhalt herunterladen. Das unterscheidet sich fundamental von Twitter/Reddit (wo Bild-URLs direkt aus den Post-Metadaten kommen). Im Plan als **separater Sub-Schritt** dokumentieren: „Telegram: file_id → getFile → temp URL → Download; Twitter/Reddit: Bild-URL direkt aus Post.“
- Ansonsten: Speicher, OCR, CLIP, Deepfake; SOCMINT nur bei `SOCMINT_INGEST_IMAGES=true`; optional `/api/search/images`.

---

## Phase 6 — Object Detection (Remote Sensing / Militär) (noch nicht umsetzen)

**Status:** Vorerst zurückgestellt. Erst nach Phase 5 bzw. bei Bedarf umsetzen.

- `hf_service.detect_objects`; GEOINT-Anbindung für militärrelevante Bilder; Doku zu Einschränkungen.

---

## Kurz: Änderungen gegenüber der ersten Planversion

| Thema | Anpassung |
|-------|-----------|
| **NEWS Dedup** | Embedding-Dedup **innerhalb** `_merge_news_results`, nach URL-Dedup, **vor** Scoring und Top-20-Cutoff. |
| **Cross-Encoder-Query** | Konfigurierbar pro Konflikt (z. B. `RANKING_QUERY_IRAN`) oder später dynamisch aus Top-Keywords/NER; kein fester String `f"{conflict} nuclear sanctions military"`. |
| **NER → FININT/GEOINT** | Klar entschieden: Supervisor **Post-Processing** nach `_collect_all_agents`, vor `_synthesize`; NER-Ergebnisse aus NEWS/SOCMINT an FININT/GEOINT weitergeben und Reports anreichern. |
| **numpy** | Phase 1–2: **kein numpy**; reines Python (sum, math.sqrt) oder scipy für Cosine; numpy erst mit pgvector irrelevant. |
| **Budget-Tracker** | Konkret: **usage.input_tokens / usage.output_tokens** aus API-Response pro Call auslesen und in monatlichen Tracker schreiben. |
| **Phase 5 Telegram** | Telegram-Bilder: **eigener Sub-Schritt** — file_id → getFile → temporäre URL (1 h gültig) → Download; getrennt von Twitter/Reddit-URL-Pfad. |
| **Error-Recovery** | Bei Haiku-Fehler **gesamten Batch** auf Fallback (regelbasiert / HF-Bulk) umschalten, nicht nur einzelnen Call mit None. |
| **HF Cold Start** | **Warmup-Call** am Anfang jedes Laufs für genutzte HF-Endpoints; **Timeout** großzügig (z. B. 30–60 s). |

---

## Dateien-Überblick (unverändert zu vorher)

- **NEU:** `backend/services/haiku_service.py`, `backend/services/hf_service.py`, optional `ner_pipeline.py`, später `storage_service.py`, `backend/migrations/001_pgvector_setup.sql`.
- **ÄNDERN:** `backend/agents/signal_framework_agent.py`, `news_agent.py` (inkl. Signatur/Parameter für `_merge_news_results`), `socmint_agent.py`, `supervisor.py` (Post-Processing NER → FININT/GEOINT), `finint_agent.py`, `geoint_agent.py`; `backend/requirements.txt` (kein numpy Phase 1–2; ggf. scipy prüfen); `backend/.env.example`, `docs/API-KEYS.md`.
