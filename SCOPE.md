# ReviewMatch — Technical Scope (prototype v0.1)

Goal of this pass: build the *engine room* of the marketplace as a runnable, tested Python package, with a synthetic evaluation harness that tells us honestly how well each part works. No web UI yet; the UI is a thin layer over these services and can come later.

## What "the product" is, technically

Four subsystems, each independently testable:

| # | Subsystem | Job | Hardest question it answers |
|---|---|---|---|
| 1 | **Domain** | Shared data model: people, works, manuscripts, journals, reviewer profiles | "What do we actually store?" |
| 2 | **Matching engine** | Manuscript in, ranked and explained reviewer shortlist out | "Who is qualified, free, and *not* conflicted?" |
| 3 | **Payments** | Compensation with a platform cut, done so money can never go missing | "Where is every penny right now?" |
| 4 | **Workflow** | The invitation lifecycle that ties matching and money together | "What happens when a reviewer accepts, ghosts, or delivers?" |

Plus an **evaluation harness** that generates a fake but realistic academic world and measures the system against known ground truth.

## Package layout

```
src/reviewmatch/
  domain/models.py         # dataclasses: Person, Work, Manuscript, Journal, ReviewerProfile, ...
  matching/
    fingerprint.py         # text -> sparse TF-IDF vector; cosine similarity
    candidates.py          # stage 1: cheap wide net (vector kNN + cited authors)
    conflicts.py           # stage 2: hard filters (COI rules on the co-authorship graph)
    ranking.py             # stage 3: weighted score + load balancing + explanations
    engine.py              # orchestrates the three stages
  payments/
    ledger.py              # double-entry ledger, integer minor units, invariants
    pricing.py             # honorarium + platform cut policy
    flows.py               # deposit / hold / release / refund / withdraw
  workflow/
    invitations.py         # state machine; transitions trigger money movements
    reliability.py         # reviewer reputation from observed behaviour
tests/                     # unit tests per subsystem
eval/
  synth.py                 # synthetic world generator with ground truth
  run_eval.py              # metrics: hit@k, COI leaks, load fairness, ledger invariants
docs/GUIDE.md              # the intuitive walkthrough
```

## Design constraints for the prototype

- **Stdlib only** (plus pytest). Sparse vectors as dicts, no numpy. Forces every mechanism to be visible and explainable.
- **Money is integers.** Pence/cents, never floats. Every movement is a balanced double-entry transaction.
- **Injectable clock.** Time is a parameter, so deadlines, expiry and load windows are testable.
- **Explainability is a feature, not a log.** Every recommendation carries the reasons it was ranked where it was.
- **Ground truth in the eval.** The synthetic world knows who the "ideal" reviewers are, so we can score the matcher instead of eyeballing it.

## What is deliberately out of scope

- Web/API layer, auth (ORCID OAuth), real OpenAlex ingestion, real embeddings (SPECTER2), Stripe/payout rails, email. Each has a clear seam in the code where it plugs in.

## Definition of "works"

- Matcher: ideal reviewers appear in the top 5 most of the time; **zero** conflicted reviewers ever recommended; invite load spread across the pool rather than concentrated.
- Payments: every transaction balances; escrow always nets to zero after settlement; platform revenue equals the sum of cuts; no state transition can move money twice.
- Workflow: illegal transitions raise; legal ones move money exactly once.

*Tags: reviewmatch, scope, architecture, cit_rep*
