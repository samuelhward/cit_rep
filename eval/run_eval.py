"""Score the prototype against synthetic ground truth and write eval/REPORT.md.

Metrics
  Matching quality    precision@k: share of the top-k that are ideal (same field, no conflict)
                      hit@1: is the #1 pick ideal?
                      random baseline: what precision@k would a coin toss get?
  Safety              COI leaks: recommended reviewers who are truly conflicted. Must be 0.
  Fairness            simulate inviting top-3 for every manuscript, with and without
                      load balancing; report max invites per reviewer and Gini coefficient.
  Money               run every invite through a randomised lifecycle and check the ledger
                      invariants: total==0, all escrow settled, revenue == sum of cuts.
  Speed               ms per match.
"""
from __future__ import annotations

import random
import statistics
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reviewmatch.matching import MatchConfig, Matcher
from reviewmatch.matching.ranking import RankingWeights
from reviewmatch.payments import PLATFORM_REVENUE, FeePolicy, Ledger, PaymentFlows
from reviewmatch.workflow import InvitationService, InvitationState

from eval.synth import World, build_world

K = 5


def gini(values: list[int]) -> float:
    xs = sorted(values)
    n = len(xs)
    if n == 0 or sum(xs) == 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return (2 * cum) / (n * sum(xs)) - (n + 1) / n


def matching_quality(world: World, matcher: Matcher) -> dict:
    p_at_k, hit1, leaks, times = [], [], 0, []
    for m in world.manuscripts:
        ideal, bad = world.ideal_reviewers(m), world.truly_conflicted(m)
        t0 = time.perf_counter()
        res = matcher.match(m)
        times.append((time.perf_counter() - t0) * 1000)
        ids = [r.reviewer.id for r in res.recommendations[:K]]
        p_at_k.append(sum(1 for i in ids if i in ideal) / K)
        hit1.append(1.0 if ids and ids[0] in ideal else 0.0)
        leaks += sum(1 for i in ids if i in bad)
    n_rev = len(world.reviewers)
    avg_ideal = statistics.mean(len(world.ideal_reviewers(m)) for m in world.manuscripts)
    return {
        f"precision@{K}": statistics.mean(p_at_k),
        "hit@1": statistics.mean(hit1),
        "random_baseline": avg_ideal / n_rev,
        "coi_leaks": leaks,
        "ms_per_match": statistics.mean(times),
    }


def load_fairness(world: World, use_balancing: bool) -> dict:
    w = RankingWeights() if use_balancing else RankingWeights(load=0.0)
    matcher = Matcher(world.people, world.works, world.reviewers, world.journals, world.today,
                      MatchConfig(top_k=3, weights=w))
    ledger = Ledger()
    flows = PaymentFlows(ledger, FeePolicy(1250))
    svc = InvitationService(world.journals, world.reviewers, flows)
    now = datetime(world.today.year, world.today.month, world.today.day, 9)
    for m in world.manuscripts:
        recent = svc.recent_invites(now - timedelta(days=30))
        for rec in matcher.match(m, recent_invites=recent).recommendations:
            svc.invite(m, rec.reviewer.id, now)
        now += timedelta(hours=6)
    counts = [0] * len(world.reviewers)
    idx = {rid: i for i, rid in enumerate(world.reviewers)}
    for inv in svc.invitations.values():
        counts[idx[inv.reviewer_id]] += 1
    invited = [c for c in counts if c]
    return {"max_invites": max(counts), "reviewers_used": len(invited),
            "gini": gini(counts), "total_invites": sum(counts)}


def money_simulation(world: World, seed: int = 1) -> dict:
    """Every manuscript invites 3 reviewers; outcomes are random; ledger must stay sane."""
    rng = random.Random(seed)
    ledger = Ledger()
    policy = FeePolicy(1250)
    flows = PaymentFlows(ledger, policy)
    now = datetime(world.today.year, world.today.month, world.today.day, 9)
    flows.deposit("pub", 50_000_000, now, "seed")
    matcher = Matcher(world.people, world.works, world.reviewers, world.journals, world.today, MatchConfig(top_k=3))
    svc = InvitationService(world.journals, world.reviewers, flows)

    outcomes = {"declined": 0, "expired": 0, "withdrawn": 0, "rejected": 0, "approved": 0}
    expected_revenue = 0
    for m in world.manuscripts:
        for rec in matcher.match(m).recommendations:
            inv = svc.invite(m, rec.reviewer.id, now)
            r = rng.random()
            if r < 0.30:
                svc.decline(inv, now + timedelta(days=1)); outcomes["declined"] += 1
            elif r < 0.38:
                outcomes["expired"] += 1                      # never answers; sweep later
            else:
                svc.accept(inv, now + timedelta(days=2))
                r2 = rng.random()
                if r2 < 0.05:
                    svc.withdraw(inv, now + timedelta(days=5)); outcomes["withdrawn"] += 1
                elif r2 < 0.12:
                    outcomes["expired"] += 1                  # accepted, never delivers
                else:
                    late = rng.random() < 0.25
                    svc.submit(inv, now + timedelta(days=28 if late else 14))
                    if rng.random() < 0.04:
                        svc.reject(inv, now + timedelta(days=30)); outcomes["rejected"] += 1
                    else:
                        svc.approve(inv, now + timedelta(days=30), rating=rng.randint(2, 5))
                        outcomes["approved"] += 1
                        expected_revenue += policy.split(world.journals["j"].honorarium_minor).platform_cut
        now += timedelta(hours=3)

    svc.expire_overdue(now + timedelta(days=365))

    escrow_open = sum(1 for a, b in ledger.balances_with_prefix("escrow:").items() if b != 0)
    reviewer_total = sum(ledger.balances_with_prefix("reviewer:").values())
    revenue = ledger.balance(PLATFORM_REVENUE)
    return {
        **outcomes,
        "transactions": len(ledger.transactions),
        "ledger_total": ledger.total(),
        "escrow_unsettled": escrow_open,
        "platform_revenue": revenue,
        "revenue_matches_expected": revenue == expected_revenue,
        "reviewer_payouts": reviewer_total,
        "publisher_spent": 50_000_000 - ledger.balance("publisher:pub"),
        "spend_reconciles": (50_000_000 - ledger.balance("publisher:pub")) == reviewer_total + revenue,
        "double_pay_attempt_noop": flows.release("inv_1", "x", now) is None,
    }


def ablations(world: World) -> dict[str, dict]:
    """Same world, different engine settings, to see what each piece buys us."""
    base = dict(people=world.people, works=world.works, reviewers=world.reviewers,
                journals=world.journals, today=world.today)
    variants = {
        "full": MatchConfig(top_k=K),
        "no_citation_bonus": MatchConfig(top_k=K, weights=RankingWeights(cited=0.0)),
        "no_conflict_filter (unsafe)": MatchConfig(top_k=K, enforce_conflicts=False),
        "no_reliability_signal": MatchConfig(top_k=K, weights=RankingWeights(reliability=0.0)),
    }
    out = {}
    for name, cfg in variants.items():
        out[name] = matching_quality(world, Matcher(**base, config=cfg))
    return out


def fmt(v):
    if isinstance(v, bool):
        return "yes" if v else "NO"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def table(rows: dict, headers=("metric", "value")) -> str:
    lines = [f"| {headers[0]} | {headers[1]} |", "|---|---|"]
    lines += [f"| {k} | {fmt(v)} |" for k, v in rows.items()]
    return "\n".join(lines)


def main() -> None:
    report = ["# Evaluation report (synthetic world)\n",
              "Generated by `python eval/run_eval.py`. Every number below comes from ground truth the "
              "synthetic world knows and the matcher does not.\n"]

    worlds = {
        "easy (disjoint vocab, topic share 0.6)": build_world(seed=7, pool_size=360, topic_share=0.6, interdisciplinary=0.0),
        "default (pool 120, topic share 0.5, 20% interdisciplinary)": build_world(seed=7),
        "hard (pool 60, topic share 0.35, 30% interdisciplinary)": build_world(seed=7, pool_size=60, topic_share=0.35, interdisciplinary=0.3),
        "brutal (pool 45, topic share 0.25, 40% interdisciplinary)": build_world(seed=7, pool_size=45, topic_share=0.25, interdisciplinary=0.4),
    }
    w0 = next(iter(worlds.values()))
    report.append(f"World size: {len(w0.reviewers)} reviewers, {len(w0.works)} works, "
                  f"{len(w0.manuscripts)} manuscripts, {len(set(w0.field_of.values()))} fields.\n")

    report.append("## 1. Matching quality by difficulty\n")
    report.append("| world | precision@5 | hit@1 | random baseline | COI leaks | ms/match |\n|---|---|---|---|---|---|")
    for name, w in worlds.items():
        m = Matcher(w.people, w.works, w.reviewers, w.journals, w.today, MatchConfig(top_k=K))
        q = matching_quality(w, m)
        report.append(f"| {name} | {q[f'precision@{K}']:.3f} | {q['hit@1']:.3f} | {q['random_baseline']:.3f} "
                      f"| {q['coi_leaks']} | {q['ms_per_match']:.1f} |")
        print(name, q)

    report.append("\n## 2. Ablations (hard world)\n")
    report.append("| variant | precision@5 | hit@1 | COI leaks |\n|---|---|---|---|")
    for name, q in ablations(worlds["hard (pool 60, topic share 0.35, 30% interdisciplinary)"]).items():
        report.append(f"| {name} | {q[f'precision@{K}']:.3f} | {q['hit@1']:.3f} | {q['coi_leaks']} |")

    report.append("\n## 3. Load fairness (default world, top-3 invited per manuscript)\n")
    report.append("| setting | total invites | reviewers used | max per reviewer | Gini |\n|---|---|---|---|---|")
    for label, flag in (("no load balancing", False), ("with load balancing", True)):
        w = build_world(seed=7)   # fresh copy: stats mutate
        f = load_fairness(w, flag)
        report.append(f"| {label} | {f['total_invites']} | {f['reviewers_used']} | {f['max_invites']} | {f['gini']:.3f} |")
        print(label, f)

    report.append("\n## 4. Money simulation (default world, randomised outcomes)\n")
    w = build_world(seed=7)
    money = money_simulation(w)
    print("money", money)
    report.append(table(money))

    report.append("\n## How to read this\n")
    report.append("- **precision@5** is the share of the five recommended reviewers who are in the right field "
                  "and genuinely conflict-free. The random baseline is what you'd get picking names from a hat.\n"
                  "- **COI leaks** must be zero. Anything else is a product-killing bug.\n"
                  "- **Gini** is 0 when every reviewer gets the same number of invites and 1 when one person gets them all.\n"
                  "- **ledger_total** must be zero (double-entry). **escrow_unsettled** must be zero after the expiry sweep.\n"
                  "- **spend_reconciles**: what publishers spent equals what reviewers got plus what the platform kept.\n")
    Path(__file__).with_name("REPORT.md").write_text("\n".join(report) + "\n")
    print("\nwrote eval/REPORT.md")


if __name__ == "__main__":
    main()
