from services.chat_feedback_store import _summarize_rows


def test_summarize_rows_includes_fallback_kpis():
    rows = [
        {
            "question_type": "risk_assessment",
            "confidence_score": 0.7,
            "helpful": True,
            "fallback_used": False,
            "created_at": "2026-04-07T10:00:00Z",
        },
        {
            "question_type": "risk_assessment",
            "confidence_score": 0.2,
            "helpful": False,
            "fallback_used": True,
            "created_at": "2026-04-07T11:00:00Z",
        },
    ]
    summary = _summarize_rows(rows)
    assert summary["fallback_total"] == 1
    assert summary["fallback_rate"] == 0.5
    assert summary["by_question_type"][0]["question_type"] == "risk_assessment"
    assert summary["by_question_type"][0]["fallback_count"] == 1
    assert summary["by_question_type"][0]["fallback_rate"] == 0.5
