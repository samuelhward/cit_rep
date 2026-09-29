"""The invitation state machine. This is where matching meets money.

    INVITED --accept--> ACCEPTED --submit--> SUBMITTED --approve--> APPROVED
       |                   |                     |
       +--decline--> DECLINED                    +--reject--> REJECTED
       +--expire---> EXPIRED (no hold yet)       |
                       +--withdraw/expire--> WITHDRAWN / EXPIRED (refund)

Money hooks (only if the journal pays):
  ACCEPTED  -> hold    (reserve the honorarium so it cannot be spent twice)
  APPROVED  -> release (pay reviewer, take platform cut)
  WITHDRAWN, EXPIRED-after-accept, REJECTED -> refund to publisher

Stats hooks feed reliability: invited, accepted, completed, on_time, rating.
Illegal transitions raise instead of silently doing nothing, because a silent no-op
on "approve" would mean a reviewer silently not getting paid.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from ..domain.models import Journal, Manuscript, ReviewerProfile
from ..payments.flows import PaymentFlows


class InvitationState(str, Enum):
    INVITED = "invited"
    DECLINED = "declined"
    ACCEPTED = "accepted"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class IllegalTransition(RuntimeError):
    pass


TERMINAL = {InvitationState.DECLINED, InvitationState.APPROVED, InvitationState.REJECTED,
            InvitationState.WITHDRAWN, InvitationState.EXPIRED}


@dataclass
class Invitation:
    id: str
    manuscript_id: str
    journal_id: str
    reviewer_id: str
    invited_at: datetime
    respond_by: datetime
    state: InvitationState = InvitationState.INVITED
    accepted_at: datetime | None = None
    due_at: datetime | None = None
    submitted_at: datetime | None = None
    history: list[tuple[InvitationState, datetime]] = field(default_factory=list)

    def _go(self, new: InvitationState, at: datetime, allowed: set[InvitationState]) -> None:
        if self.state not in allowed:
            raise IllegalTransition(f"{self.id}: cannot go {self.state.value} -> {new.value}")
        self.state = new
        self.history.append((new, at))


class InvitationService:
    """Owns all invitations; applies transitions; triggers money and stats side effects."""

    def __init__(self, journals: dict[str, Journal], reviewers: dict[str, ReviewerProfile],
                 flows: PaymentFlows, respond_days: int = 7) -> None:
        self.journals = journals
        self.reviewers = reviewers
        self.flows = flows
        self.respond_days = respond_days
        self.invitations: dict[str, Invitation] = {}
        self._seq = 0

    # --- queries used by the matcher for load balancing -------------------------------
    def recent_invites(self, since: datetime) -> dict[str, int]:
        out: dict[str, int] = {}
        for inv in self.invitations.values():
            if inv.invited_at >= since:
                out[inv.reviewer_id] = out.get(inv.reviewer_id, 0) + 1
        return out

    def accepted_in_month(self, year: int, month: int) -> dict[str, int]:
        out: dict[str, int] = {}
        for inv in self.invitations.values():
            if inv.accepted_at and (inv.accepted_at.year, inv.accepted_at.month) == (year, month):
                out[inv.reviewer_id] = out.get(inv.reviewer_id, 0) + 1
        return out

    # --- transitions --------------------------------------------------------------------
    def invite(self, manuscript: Manuscript, reviewer_id: str, at: datetime) -> Invitation:
        self._seq += 1
        inv = Invitation(id=f"inv_{self._seq}", manuscript_id=manuscript.id,
                         journal_id=manuscript.journal_id, reviewer_id=reviewer_id,
                         invited_at=at, respond_by=at + timedelta(days=self.respond_days))
        inv.history.append((InvitationState.INVITED, at))
        self.invitations[inv.id] = inv
        self.reviewers[reviewer_id].stats.invited += 1
        return inv

    def decline(self, inv: Invitation, at: datetime) -> None:
        inv._go(InvitationState.DECLINED, at, {InvitationState.INVITED})

    def accept(self, inv: Invitation, at: datetime) -> None:
        inv._go(InvitationState.ACCEPTED, at, {InvitationState.INVITED})
        journal = self.journals[inv.journal_id]
        inv.accepted_at = at
        inv.due_at = at + timedelta(days=journal.review_days)
        self.reviewers[inv.reviewer_id].stats.accepted += 1
        self.flows.hold(journal.publisher_id, inv.id, journal.honorarium_minor, at)

    def submit(self, inv: Invitation, at: datetime) -> None:
        inv._go(InvitationState.SUBMITTED, at, {InvitationState.ACCEPTED})
        inv.submitted_at = at
        stats = self.reviewers[inv.reviewer_id].stats
        stats.completed += 1
        if inv.due_at and at <= inv.due_at:
            stats.on_time += 1

    def approve(self, inv: Invitation, at: datetime, rating: int | None = None):
        inv._go(InvitationState.APPROVED, at, {InvitationState.SUBMITTED})
        reviewer = self.reviewers[inv.reviewer_id]
        if rating is not None:
            reviewer.stats.rating_sum += rating
            reviewer.stats.rating_count += 1
        return self.flows.release(inv.id, inv.reviewer_id, at, reviewer.preferences.charity_id)

    def reject(self, inv: Invitation, at: datetime) -> int:
        """Editor judged the review unusable. No pay; publisher refunded."""
        inv._go(InvitationState.REJECTED, at, {InvitationState.SUBMITTED})
        return self.flows.refund(inv.id, self.journals[inv.journal_id].publisher_id, at)

    def withdraw(self, inv: Invitation, at: datetime) -> int:
        inv._go(InvitationState.WITHDRAWN, at, {InvitationState.ACCEPTED})
        return self.flows.refund(inv.id, self.journals[inv.journal_id].publisher_id, at)

    def expire_overdue(self, now: datetime) -> list[Invitation]:
        """Sweep: unanswered invites past respond_by, and accepted reviews long past due."""
        expired = []
        for inv in self.invitations.values():
            if inv.state == InvitationState.INVITED and now > inv.respond_by:
                inv._go(InvitationState.EXPIRED, now, {InvitationState.INVITED})
                expired.append(inv)
            elif inv.state == InvitationState.ACCEPTED and inv.due_at and now > inv.due_at + timedelta(days=14):
                inv._go(InvitationState.EXPIRED, now, {InvitationState.ACCEPTED})
                self.flows.refund(inv.id, self.journals[inv.journal_id].publisher_id, now)
                expired.append(inv)
        return expired
