from datetime import datetime, timedelta

import pytest

from reviewmatch.domain.models import Journal, Manuscript, Person, ReviewerProfile, ReviewerStats
from reviewmatch.payments import FeePolicy, Ledger, PaymentFlows, PLATFORM_REVENUE
from reviewmatch.workflow import IllegalTransition, InvitationService, InvitationState, reliability_score

T0 = datetime(2026, 9, 1, 9)


def _svc(honorarium=2_000):
    ledger = Ledger()
    flows = PaymentFlows(ledger, FeePolicy(1250))
    flows.deposit("pub", 100_000, T0, "seed")
    journals = {"j": Journal("j", "J", "pub", honorarium_minor=honorarium, review_days=21)}
    reviewers = {"r": ReviewerProfile(Person("r", "Rev"))}
    svc = InvitationService(journals, reviewers, flows)
    ms = Manuscript("m", "t", "a", ("auth",), "j")
    return svc, ledger, ms


def test_happy_path_pays_once_and_records_stats():
    svc, ledger, ms = _svc()
    inv = svc.invite(ms, "r", T0)
    svc.accept(inv, T0 + timedelta(days=1))
    assert ledger.balance("escrow:inv_1") == 2_000
    svc.submit(inv, T0 + timedelta(days=10))
    split = svc.approve(inv, T0 + timedelta(days=11), rating=5)
    assert inv.state == InvitationState.APPROVED
    assert split.reviewer_net == 1_750
    assert ledger.balance("reviewer:r") == 1_750
    assert ledger.balance(PLATFORM_REVENUE) == 250
    assert ledger.balance("escrow:inv_1") == 0
    s = svc.reviewers["r"].stats
    assert (s.invited, s.accepted, s.completed, s.on_time, s.rating_count) == (1, 1, 1, 1, 1)
    assert ledger.total() == 0


def test_late_submission_not_counted_on_time():
    svc, _, ms = _svc()
    inv = svc.invite(ms, "r", T0); svc.accept(inv, T0)
    svc.submit(inv, T0 + timedelta(days=30))
    assert svc.reviewers["r"].stats.on_time == 0


def test_illegal_transitions_raise():
    svc, _, ms = _svc()
    inv = svc.invite(ms, "r", T0)
    with pytest.raises(IllegalTransition):
        svc.submit(inv, T0)          # never accepted
    with pytest.raises(IllegalTransition):
        svc.approve(inv, T0)         # never submitted
    svc.decline(inv, T0)
    with pytest.raises(IllegalTransition):
        svc.accept(inv, T0)          # already declined


def test_withdraw_and_reject_refund_publisher():
    svc, ledger, ms = _svc()
    a = svc.invite(ms, "r", T0); svc.accept(a, T0); svc.withdraw(a, T0)
    b = svc.invite(ms, "r", T0); svc.accept(b, T0); svc.submit(b, T0); svc.reject(b, T0)
    assert ledger.balance("publisher:pub") == 100_000
    assert ledger.balance("reviewer:r") == 0
    assert ledger.total() == 0


def test_unpaid_journal_moves_no_money():
    svc, ledger, ms = _svc(honorarium=0)
    inv = svc.invite(ms, "r", T0); svc.accept(inv, T0); svc.submit(inv, T0); svc.approve(inv, T0)
    assert len(ledger.transactions) == 1   # only the seed deposit


def test_expiry_sweep():
    svc, ledger, ms = _svc()
    a = svc.invite(ms, "r", T0)                                  # never answered
    b = svc.invite(ms, "r", T0); svc.accept(b, T0)               # accepted, never delivered
    expired = svc.expire_overdue(T0 + timedelta(days=60))
    assert {i.id for i in expired} == {"inv_1", "inv_2"}
    assert ledger.balance("publisher:pub") == 100_000            # refunded


def test_reliability_prior_and_movement():
    fresh = reliability_score(ReviewerStats())
    good = reliability_score(ReviewerStats(invited=10, accepted=10, completed=10, on_time=10, rating_sum=50, rating_count=10))
    bad = reliability_score(ReviewerStats(invited=10, accepted=1, completed=1, on_time=0, rating_sum=1, rating_count=1))
    assert bad < fresh < good
    assert 0 <= bad and good <= 1
