from agents.research_normalizer import normalize_research_enrichments


def test_normalizer_rejects_item_without_source_url():
    applied, rejected, ratio = normalize_research_enrichments(
        [{"field_path": "news.summary", "value": "x", "source_title": "no url", "fetched_at": "2026-01-01T00:00:00Z"}]
    )
    assert applied == []
    assert len(rejected) == 1
    assert ratio == 0.0


def test_normalizer_accepts_item_with_valid_url():
    applied, rejected, ratio = normalize_research_enrichments(
        [
            {
                "field_path": "news.summary",
                "value": "Updated fact",
                "source_url": "https://example.com/report",
                "source_title": "Example report",
                "fetched_at": "2026-01-01T00:00:00Z",
                "confidence": 72.0,
            }
        ]
    )
    assert len(applied) == 1
    assert rejected == []
    assert ratio == 1.0
