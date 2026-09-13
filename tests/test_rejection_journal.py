"""Tests for the RejectionJournal module."""

import pytest
from tradebot_sci.runtime.rejection_journal import RejectionJournal


@pytest.fixture
def journal():
    """Fresh journal instance for each test (not the singleton)."""
    return RejectionJournal(maxlen=10)


class TestRejectionJournal:

    def test_log_and_summary(self, journal):
        journal.log("EUR_USD", "5m", "Greed Guard", "Daily goal met")
        journal.log("GBP_USD", "5m", "Churn Burner", "Max 3/hr")
        journal.log("EUR_USD", "15m", "Greed Guard", "Daily goal met")

        summary = journal.get_summary()
        assert summary["Greed Guard"] == 2
        assert summary["Churn Burner"] == 1
        assert journal.total_rejections == 3

    def test_ring_buffer_maxlen(self, journal):
        """Buffer should not grow beyond maxlen."""
        for i in range(25):
            journal.log("SYM", "1m", "Gate", f"reason_{i}")

        recent = journal.get_recent(100)  # ask for more than maxlen
        assert len(recent) == 10  # capped at maxlen
        # Most recent should be the last logged
        assert recent[-1].reason == "reason_24"

    def test_get_recent_subset(self, journal):
        for i in range(5):
            journal.log("SYM", "1m", "Gate", f"reason_{i}")

        recent = journal.get_recent(3)
        assert len(recent) == 3
        assert recent[-1].reason == "reason_4"

    def test_reset_clears_all(self, journal):
        journal.log("EUR_USD", "5m", "X", "test")
        journal.reset()

        assert journal.total_rejections == 0
        assert journal.get_summary() == {}
        assert journal.get_recent() == []

    def test_empty_journal(self, journal):
        assert journal.total_rejections == 0
        assert journal.get_summary() == {}
        assert journal.get_recent() == []

    def test_score_and_grade_stored(self, journal):
        journal.log("BTC_USD", "1h", "Score Gate", "Below threshold", score=42.5, grade="C")

        entry = journal.get_recent(1)[0]
        assert entry.score == 42.5
        assert entry.grade == "C"
        assert entry.symbol == "BTC_USD"
