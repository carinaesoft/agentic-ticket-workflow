import contextlib
import random
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.helpdesk import FakeHelpdesk, HelpdeskRejected, HelpdeskTransientError
from app.domain.models import ActionKind, CloseAction, EscalateAction, RefundAction, ReplyAction

REFUND = RefundAction(invoice_id="INV-1002", amount_eur=Decimal("49.00"))


class SequenceRandom(random.Random):
    """``random()`` returns the given values in order."""

    def __init__(self, values: list[float]) -> None:
        super().__init__()
        self._values = list(values)

    def random(self) -> float:
        return self._values.pop(0)


def test_rate_zero_always_succeeds() -> None:
    helpdesk = FakeHelpdesk(failure_rate=0, lost_response_rate=0, rng=random.Random(1))
    for n, action in enumerate(
        [
            ReplyAction(message="hi", article_ids=["KB-1"]),
            REFUND,
            EscalateAction(reason="x"),
            CloseAction(reason="y"),
        ]
    ):
        result = helpdesk.perform(f"wf-{n}:{action.kind}", action)
        assert result.kind == ActionKind(action.kind)
        assert result.idempotency_key == f"wf-{n}:{action.kind}"
        assert result.helpdesk_reference.startswith("HD-")
    assert len(helpdesk.replies) == len(helpdesk.refunds) == 1
    assert len(helpdesk.escalations) == len(helpdesk.closures) == 1


def test_rate_one_fails_before_any_effect() -> None:
    helpdesk = FakeHelpdesk(failure_rate=1, rng=random.Random(1))
    with pytest.raises(HelpdeskTransientError, match="temporarily unavailable"):
        helpdesk.perform("wf:refund", REFUND)
    assert helpdesk.refunds == []


def test_lost_response_records_effect_and_retry_returns_stored_result() -> None:
    helpdesk = FakeHelpdesk(
        failure_rate=0.5, lost_response_rate=0.5, rng=SequenceRandom([0.9, 0.1])
    )
    with pytest.raises(HelpdeskTransientError, match="response lost"):
        helpdesk.perform("ticket-T-2:refund", REFUND)
    assert len(helpdesk.refunds) == 1

    result = helpdesk.perform("ticket-T-2:refund", REFUND)
    assert result.outcome_message == "refund of 49.00 EUR issued for INV-1002"
    assert len(helpdesk.refunds) == 1


def test_lookup_returns_result_recorded_before_the_response_was_lost() -> None:
    helpdesk = FakeHelpdesk(
        failure_rate=0.5, lost_response_rate=0.5, rng=SequenceRandom([0.9, 0.1])
    )
    assert helpdesk.lookup("ticket-T-2:refund") is None
    with pytest.raises(HelpdeskTransientError, match="response lost"):
        helpdesk.perform("ticket-T-2:refund", REFUND)

    found = helpdesk.lookup("ticket-T-2:refund")
    assert found is not None
    assert found.idempotency_key == "ticket-T-2:refund"
    assert found.outcome_message == "refund of 49.00 EUR issued for INV-1002"
    assert helpdesk.lookup("ticket-T-3:refund") is None
    assert len(helpdesk.refunds) == 1  # a lookup never applies anything


def test_lookup_finds_nothing_when_the_call_failed_before_the_effect() -> None:
    helpdesk = FakeHelpdesk(failure_rate=1, rng=random.Random(1))
    with pytest.raises(HelpdeskTransientError, match="temporarily unavailable"):
        helpdesk.perform("wf:refund", REFUND)
    assert helpdesk.lookup("wf:refund") is None


def test_stored_result_is_returned_even_while_failing() -> None:
    helpdesk = FakeHelpdesk(rng=random.Random(1))
    first = helpdesk.perform("k:refund", REFUND)
    helpdesk.failure_rate = 1
    assert helpdesk.perform("k:refund", REFUND) == first
    assert len(helpdesk.refunds) == 1


def test_key_reused_for_a_different_action_is_rejected() -> None:
    helpdesk = FakeHelpdesk(rng=random.Random(1))
    helpdesk.perform("k:refund", REFUND)
    other = RefundAction(invoice_id="INV-1002", amount_eur=Decimal("1.00"))
    with pytest.raises(HelpdeskRejected):
        helpdesk.perform("k:refund", other)
    assert len(helpdesk.refunds) == 1


def test_new_instance_on_the_same_file_returns_the_result_whose_response_was_lost(
    tmp_path: Path,
) -> None:
    path = str(tmp_path / "store.db")
    first = FakeHelpdesk(lost_response_rate=1.0, rng=random.Random(1), store_path=path)
    with pytest.raises(HelpdeskTransientError, match="response lost"):
        first.perform("ticket-T-2:refund", REFUND)
    recorded = first.lookup("ticket-T-2:refund")
    assert recorded is not None

    second = FakeHelpdesk(rng=random.Random(1), store_path=path)
    result = second.perform("ticket-T-2:refund", REFUND)

    assert result.helpdesk_reference == recorded.helpdesk_reference
    assert len(first.refunds) == 1
    assert len(second.refunds) == 0
    with contextlib.closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT COUNT(*) FROM helpdesk_actions").fetchone() == (1,)


def test_seeded_rng_is_deterministic() -> None:
    def outcomes(seed: int) -> list[str]:
        helpdesk = FakeHelpdesk(0.4, 0.3, rng=random.Random(seed))
        seen = []
        for n in range(30):
            try:
                helpdesk.perform(f"wf-{n}:close", CloseAction(reason="r"))
                seen.append("ok")
            except HelpdeskTransientError as exc:
                seen.append(str(exc))
        return seen

    assert outcomes(7) == outcomes(7)
    assert "ok" in outcomes(7)
    assert any("lost" in o for o in outcomes(7))
    assert outcomes(7) != outcomes(8)
