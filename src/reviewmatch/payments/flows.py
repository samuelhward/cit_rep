"""The five money movements the marketplace needs, as named ledger transactions.

Accounts (strings, namespaced by prefix):
  external                 the outside world (bank). Goes negative as publishers deposit.
  publisher:<id>           a publisher's prepaid balance
  escrow:<invitation_id>   money reserved for one specific review
  reviewer:<id>            a reviewer's withdrawable balance
  charity:<id>             a charity a reviewer has chosen to route fees to
  platform:revenue         our cut

Lifecycle of one paid review:
  deposit  external -> publisher            (publisher tops up)
  hold     publisher -> escrow              (reviewer accepts: money is reserved)
  release  escrow -> reviewer + platform    (editor approves the review)
  refund   escrow -> publisher              (reviewer withdraws or times out)
  withdraw reviewer -> external             (reviewer cashes out)

Each uses a deterministic idempotency key so a retry can never double-move money.
"""
from __future__ import annotations

from datetime import datetime

from .ledger import Ledger, Leg
from .pricing import FeePolicy, Split

EXTERNAL = "external"
PLATFORM_REVENUE = "platform:revenue"


class InsufficientFunds(ValueError):
    pass


class PaymentFlows:
    def __init__(self, ledger: Ledger, policy: FeePolicy) -> None:
        self.ledger = ledger
        self.policy = policy

    # --- account name helpers ---------------------------------------------------
    @staticmethod
    def publisher(pid: str) -> str: return f"publisher:{pid}"
    @staticmethod
    def escrow(inv_id: str) -> str: return f"escrow:{inv_id}"
    @staticmethod
    def reviewer(rid: str) -> str: return f"reviewer:{rid}"
    @staticmethod
    def charity(cid: str) -> str: return f"charity:{cid}"

    # --- movements ------------------------------------------------------------------
    def deposit(self, publisher_id: str, amount: int, at: datetime, ref: str) -> None:
        self.ledger.post(f"deposit:{ref}", f"deposit by {publisher_id}",
                         [Leg(EXTERNAL, -amount), Leg(self.publisher(publisher_id), amount)], at)

    def hold(self, publisher_id: str, invitation_id: str, amount: int, at: datetime) -> None:
        if amount == 0:
            return
        if self.ledger.balance(self.publisher(publisher_id)) < amount:
            raise InsufficientFunds(f"{publisher_id} cannot cover {amount}")
        self.ledger.post(f"hold:{invitation_id}", f"escrow for {invitation_id}",
                         [Leg(self.publisher(publisher_id), -amount),
                          Leg(self.escrow(invitation_id), amount)], at)

    def release(self, invitation_id: str, reviewer_id: str, at: datetime,
                charity_id: str | None = None) -> Split | None:
        gross = self.ledger.balance(self.escrow(invitation_id))
        if gross == 0:
            return None
        split = self.policy.split(gross)
        payee = self.charity(charity_id) if charity_id else self.reviewer(reviewer_id)
        legs = [Leg(self.escrow(invitation_id), -gross), Leg(payee, split.reviewer_net)]
        if split.platform_cut:
            legs.append(Leg(PLATFORM_REVENUE, split.platform_cut))
        self.ledger.post(f"release:{invitation_id}", f"payout for {invitation_id}", legs, at)
        return split

    def refund(self, invitation_id: str, publisher_id: str, at: datetime) -> int:
        amount = self.ledger.balance(self.escrow(invitation_id))
        if amount == 0:
            return 0
        self.ledger.post(f"refund:{invitation_id}", f"refund escrow {invitation_id}",
                         [Leg(self.escrow(invitation_id), -amount),
                          Leg(self.publisher(publisher_id), amount)], at)
        return amount

    def withdraw(self, reviewer_id: str, amount: int, at: datetime, ref: str) -> None:
        if self.ledger.balance(self.reviewer(reviewer_id)) < amount:
            raise InsufficientFunds(f"{reviewer_id} cannot withdraw {amount}")
        self.ledger.post(f"withdraw:{ref}", f"payout to {reviewer_id}",
                         [Leg(self.reviewer(reviewer_id), -amount), Leg(EXTERNAL, amount)], at)
