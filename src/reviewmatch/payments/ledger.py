"""A double-entry ledger in ~60 lines.

Rules that make money impossible to lose:
  1. Amounts are integers in minor units (pence). Floats never touch money.
  2. Every transaction has legs that sum to exactly zero. Money moves; it is never
     created or destroyed inside the ledger. (Money enters/leaves via the EXTERNAL account.)
  3. Transactions are append-only. Mistakes are fixed by posting a reversing transaction.
  4. Idempotency keys: posting the same key twice is a no-op, so a retried "release
     payment" call cannot pay a reviewer twice.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


class UnbalancedTransaction(ValueError):
    pass


@dataclass(frozen=True)
class Leg:
    account: str
    amount: int          # positive = account gains, negative = account loses


@dataclass(frozen=True)
class Transaction:
    key: str             # idempotency key, e.g. "release:inv_42"
    memo: str
    legs: tuple[Leg, ...]
    at: datetime


@dataclass
class Ledger:
    transactions: list[Transaction] = field(default_factory=list)
    _balances: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _keys: set[str] = field(default_factory=set)

    def post(self, key: str, memo: str, legs: list[Leg], at: datetime) -> Transaction | None:
        """Append a balanced transaction. Returns None if `key` was already posted."""
        if key in self._keys:
            return None
        if any(not isinstance(l.amount, int) for l in legs):
            raise TypeError("amounts must be integers in minor units")
        if sum(l.amount for l in legs) != 0:
            raise UnbalancedTransaction(f"{key}: legs sum to {sum(l.amount for l in legs)}")
        tx = Transaction(key, memo, tuple(legs), at)
        self.transactions.append(tx)
        self._keys.add(key)
        for l in legs:
            self._balances[l.account] += l.amount
        return tx

    def balance(self, account: str) -> int:
        return self._balances.get(account, 0)

    def balances_with_prefix(self, prefix: str) -> dict[str, int]:
        return {a: b for a, b in self._balances.items() if a.startswith(prefix)}

    def total(self) -> int:
        """Sum of all balances. Always zero if the ledger is healthy."""
        return sum(self._balances.values())

    def history(self, account: str) -> list[Transaction]:
        return [t for t in self.transactions if any(l.account == account for l in t.legs)]
