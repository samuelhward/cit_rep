"""Walk one manuscript through the whole system and print what happens.

    python demo.py
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from eval.synth import build_world
from reviewmatch.matching import MatchConfig, Matcher
from reviewmatch.payments import PLATFORM_REVENUE, FeePolicy, Ledger, PaymentFlows
from reviewmatch.workflow import InvitationService

world = build_world(seed=7, pool_size=60, topic_share=0.35, interdisciplinary=0.3)
ms = world.manuscripts[3]
now = datetime(2026, 9, 29, 9)

print(f"Manuscript {ms.id}  field={world.manuscript_field[ms.id]}  authors={ms.author_ids}")
print(f"  title: {ms.title[:70]}...\n")

matcher = Matcher(world.people, world.works, world.reviewers, world.journals, world.today, MatchConfig(top_k=5))
res = matcher.match(ms)
print(f"Stage 1 cast a net of {res.n_candidates} candidates; stage 2 removed {len(res.excluded)}:")
for rid, cs in list(res.excluded.items())[:5]:
    print(f"  - {rid:6s} {', '.join(c.detail for c in cs)}")
print("\nStage 3 ranked the survivors:")
for i, r in enumerate(res.recommendations, 1):
    truth = "ideal" if r.reviewer.id in world.ideal_reviewers(ms) else "field " + str(world.field_of[r.reviewer.id])
    print(f"  {i}. {r.reviewer.id:6s} score={r.score:.3f}  [{truth}]  {'; '.join(r.reasons)}")

print("\nNow the money. Journal pays £150.00 per review; platform takes 12.5%.")
ledger = Ledger()
flows = PaymentFlows(ledger, FeePolicy(platform_rate_bps=1250))
flows.deposit("pub", 100_000, now, "topup-1")
svc = InvitationService(world.journals, world.reviewers, flows)

top = res.recommendations[0].reviewer.id
inv = svc.invite(ms, top, now)
svc.accept(inv, now + timedelta(days=1))
print(f"  accepted  -> publisher {ledger.balance('publisher:pub'):>7}  escrow {ledger.balance('escrow:' + inv.id):>6}")
svc.submit(inv, now + timedelta(days=12))
split = svc.approve(inv, now + timedelta(days=13), rating=5)
print(f"  approved  -> reviewer {ledger.balance('reviewer:' + top):>8}  platform {ledger.balance(PLATFORM_REVENUE):>5}  escrow {ledger.balance('escrow:' + inv.id)}")
print(f"  split: gross {split.gross}, cut {split.platform_cut}, net {split.reviewer_net}")
print(f"  ledger total (must be 0): {ledger.total()}")
print("\nLedger:")
for t in ledger.transactions:
    print(f"  {t.key:16s} " + "  ".join(f"{l.account}{l.amount:+d}" for l in t.legs))
