from datetime import datetime

import pytest

from reviewmatch.payments import EXTERNAL, PLATFORM_REVENUE, FeePolicy, Ledger, Leg, PaymentFlows, UnbalancedTransaction
from reviewmatch.payments.flows import InsufficientFunds

T = datetime(2026, 9, 29, 12)


def test_unbalanced_transaction_rejected():
    with pytest.raises(UnbalancedTransaction):
        Ledger().post("k", "bad", [Leg("a", 5), Leg("b", -4)], T)


def test_floats_rejected():
    with pytest.raises(TypeError):
        Ledger().post("k", "bad", [Leg("a", 5.0), Leg("b", -5.0)], T)


def test_idempotent_post():
    l = Ledger()
    assert l.post("k", "x", [Leg("a", 5), Leg("b", -5)], T) is not None
    assert l.post("k", "x", [Leg("a", 5), Leg("b", -5)], T) is None
    assert l.balance("a") == 5


def test_split_rounds_down_for_platform():
    s = FeePolicy(platform_rate_bps=1250).split(999)   # 12.5% of 999 = 124.875
    assert (s.platform_cut, s.reviewer_net) == (124, 875)
    assert s.platform_cut + s.reviewer_net == s.gross


def test_split_min_cut_never_exceeds_gross():
    s = FeePolicy(platform_rate_bps=0, min_cut_minor=500).split(300)
    assert (s.platform_cut, s.reviewer_net) == (300, 0)


def test_full_paid_lifecycle():
    l = Ledger()
    f = PaymentFlows(l, FeePolicy(1250))
    f.deposit("pub", 10_000, T, "d1")
    f.hold("pub", "inv_1", 2_000, T)
    assert l.balance("publisher:pub") == 8_000
    assert l.balance("escrow:inv_1") == 2_000
    split = f.release("inv_1", "rev", T)
    assert split.reviewer_net == 1_750 and split.platform_cut == 250
    assert l.balance("escrow:inv_1") == 0
    assert l.balance("reviewer:rev") == 1_750
    assert l.balance(PLATFORM_REVENUE) == 250
    f.withdraw("rev", 1_750, T, "w1")
    assert l.balance("reviewer:rev") == 0
    assert l.balance(EXTERNAL) == -10_000 + 1_750
    assert l.total() == 0


def test_release_twice_is_a_noop():
    l = Ledger(); f = PaymentFlows(l, FeePolicy(1000))
    f.deposit("pub", 1_000, T, "d"); f.hold("pub", "i", 1_000, T)
    f.release("i", "r", T); f.release("i", "r", T)
    assert l.balance("reviewer:r") == 900 and l.balance(PLATFORM_REVENUE) == 100


def test_refund_returns_escrow_to_publisher():
    l = Ledger(); f = PaymentFlows(l, FeePolicy(1000))
    f.deposit("pub", 1_000, T, "d"); f.hold("pub", "i", 600, T)
    assert f.refund("i", "pub", T) == 600
    assert l.balance("publisher:pub") == 1_000 and l.balance("escrow:i") == 0


def test_charity_routing():
    l = Ledger(); f = PaymentFlows(l, FeePolicy(1000))
    f.deposit("pub", 1_000, T, "d"); f.hold("pub", "i", 1_000, T)
    f.release("i", "r", T, charity_id="msf")
    assert l.balance("charity:msf") == 900 and l.balance("reviewer:r") == 0


def test_hold_requires_funds():
    l = Ledger(); f = PaymentFlows(l, FeePolicy(1000))
    with pytest.raises(InsufficientFunds):
        f.hold("pub", "i", 1, T)
