# The Guide: how ReviewMatch works

This walks through what has been built, in layers. Level 0 is one paragraph. Level 4 is the actual mechanics with pointers into the code. Stop at whichever level you need; each one is complete on its own.

---

## Level 0: the elevator

An editor pastes a manuscript. The system finds the people who know that topic, throws out everyone who has a conflict of interest, ranks the rest, and shows the top five with reasons. The editor invites one. When the reviewer accepts, the journal's money for that review is locked in a vault. When the editor approves the finished review, the vault opens: most goes to the reviewer, a slice goes to the platform. Every penny is tracked so that nothing can be lost, double-paid or invented.

---

## Level 1: the four boxes

```
   manuscript
       |
       v
 [ MATCHING ]  -->  shortlist  -->  [ WORKFLOW ]  -->  [ PAYMENTS ]
  who fits?          top 5          invite/accept/       hold/release/
  who's conflicted?                 submit/approve       refund, with a cut
                                          ^
                                          |
                                    [ DOMAIN ]
                             people, papers, manuscripts,
                             journals, reviewer profiles
```

- **Domain** is the vocabulary: the nouns everything else talks about. `src/reviewmatch/domain/models.py`
- **Matching** turns a manuscript into a ranked shortlist. `src/reviewmatch/matching/`
- **Workflow** is the lifecycle of one invitation, from "would you?" to "paid". `src/reviewmatch/workflow/`
- **Payments** is a tiny bank. `src/reviewmatch/payments/`

Plus an **evaluation harness** (`eval/`) that builds a fake academic world and scores the system against known right answers.

---

## Level 2: each box, by analogy

### Matching: a recruiter with a blacklist

Think of hiring a contractor. You do three things in order:

1. **Cast a wide net.** Look for anyone whose past work resembles the job. You also look at who the client already mentioned by name (in our case: who the manuscript *cites*). This is stage 1, *candidate generation*.
2. **Apply the hard rules.** No relatives, no one who works for the client, no one who's already fully booked. These are not "minus points"; they are disqualifications. This is stage 2, the *conflict filter*.
3. **Rank the survivors.** Best fit first, but also prefer people who show up on time, and do not keep calling the same three people. This is stage 3, *ranking*.

The order matters. Hard rules come *after* the wide net because checking every rule on every reviewer in the world is slow. They come *before* ranking because a conflicted reviewer with a perfect score is still a conflicted reviewer.

### Conflicts: a family tree for papers

Two academics are connected if they have written a paper together. Chain enough of those and you get a graph: the *co-authorship graph*. A conflict of interest is mostly a question of "how close are you in this graph, and how recently?". The prototype also records three things the graph cannot see: same institution, supervisor/student, shared grant. Each rule produces a sentence an editor can read ("co-authored with Alice in 2024"), because "excluded, score 0" is not something anyone will trust.

### Reliability: a credit score for reviewers

You do not ask reviewers if they are reliable. You watch. Do they accept invitations? Do they deliver on time? Do editors rate their reviews well? Three rates, blended into one number.

The subtlety: a brand-new reviewer has no history. 0 out of 0 is not a number. So we pretend everyone starts with a few average outcomes already on their record (a *prior*). A new reviewer scores like an average reviewer; after ten real reviews the prior barely matters. This is the same trick as "a restaurant with one 5-star review is not better than one with 500 reviews averaging 4.7".

### Payments: a vault with a receipt for every move

Picture the money as physical coins that can only be moved, never created or destroyed. Every account is a jar. Every transaction takes coins out of one or more jars and puts the *same number* into others. If the totals ever disagree, the transaction is refused.

The jars:

| Jar | Holds |
|---|---|
| `external` | the outside world (a bank). Goes negative as money comes in. |
| `publisher:<id>` | a publisher's prepaid balance |
| `escrow:<invitation>` | money reserved for one specific review |
| `reviewer:<id>` | what a reviewer can withdraw |
| `charity:<id>` | where a reviewer can choose to send their fee instead |
| `platform:revenue` | our cut |

The lifecycle of one paid review is five moves: **deposit** (bank to publisher), **hold** (publisher to escrow, when the reviewer accepts), **release** (escrow to reviewer + platform, when the review is approved), or **refund** (escrow back to publisher, if it falls through), and **withdraw** (reviewer to bank).

Why escrow at all? Because "the publisher will pay later" is a promise, and promises are where marketplaces die. Holding the money the moment a reviewer commits means the reviewer knows the money exists, and the publisher cannot promise the same £150 to two people.

### Workflow: a board game with fixed moves

An invitation is a token on a board with eight squares. It starts on INVITED and can only move along the drawn lines:

```
INVITED --accept--> ACCEPTED --submit--> SUBMITTED --approve--> APPROVED
   |                   |                     |
   +--decline--> DECLINED                    +--reject--> REJECTED
   +--expire---> EXPIRED                     
                       +--withdraw--> WITHDRAWN
                       +--expire----> EXPIRED
```

Some squares trigger money: landing on ACCEPTED holds the escrow; APPROVED releases it; WITHDRAWN, REJECTED or EXPIRED-after-accept refund it. Trying an illegal move (approving something never submitted) throws an error rather than quietly doing nothing, because a quiet nothing here means a reviewer quietly does not get paid.

---

## Level 3: the mechanisms

### How "topic fit" is computed

**Step 1: text to word bag.** Lowercase, split into words, drop stopwords ("the", "we", "results"). `matching/fingerprint.py: tokenize`

**Step 2: weight the words.** A word that appears in every abstract ("method") tells you nothing about topic. A word that appears in few ("crispr") tells you a lot. TF-IDF does exactly this: *term frequency* (how often in this text) times *inverse document frequency* (how rare across all texts). The result is a sparse vector: a dictionary of `word -> weight`. `Vectorizer.fit` learns the rarity; `Vectorizer.vectorize` applies it.

**Step 3: a reviewer's fingerprint.** Vectorize each of their papers, add them up, but weight recent papers more: a paper from 5 years ago counts half, from 10 years ago a quarter (`half_life_years=5`). Someone who switched fields is represented by where they are now. `matching/candidates.py: ReviewerIndex._build`

**Step 4: compare.** Cosine similarity: the angle between two vectors. 1.0 means identical direction (same topic mix), 0.0 means nothing in common. Length does not matter, so a long abstract and a short one compare fairly. `fingerprint.py: cosine`

This is deliberately the simplest thing that works. The real product swaps step 1-2 for a neural embedding (SPECTER2, trained on scientific papers) that understands synonyms. The interface stays the same: text in, vector out, cosine to compare.

### How candidates are generated

Two routes, union of results. `matching/candidates.py: ReviewerIndex.generate`

- **Similarity route.** Compute the manuscript vector, compare against every reviewer vector, keep the top 200 above a minimum fit.
- **Citation route.** For every work the manuscript cites, look up its authors. If they are reviewers, add them (even if similarity was low) and note which of their works were cited.

The citation route is the one that catches "this person uses different words for the same idea". It is also the one the evaluation flags as double-edged (see ASSESSMENT.md).

### How conflicts are checked

`matching/conflicts.py: ConflictChecker.check`. Rules run cheapest first and each returns a `Conflict(rule, detail)`:

| Rule | Data it needs | Where that data comes from in production |
|---|---|---|
| author | manuscript author list | submission system |
| opted_out / payment_pref / capacity / unavailable | reviewer preferences | reviewer's own profile |
| coauthor (within 5 years) | co-authorship graph | OpenAlex, good coverage |
| institution | affiliations | ORCID, patchy |
| advisor | supervisor links | mostly self-declared |
| grant | funding | mostly self-declared |

The co-authorship graph is built once (`CoauthorGraph`) as a dictionary from `(person_a, person_b)` to the most recent year they wrote together. Lookup is instant.

### How ranking works

`matching/ranking.py: score_candidate`. One formula:

```
score = 0.55 * fit  +  0.15 * cited  +  0.20 * reliability  -  0.10 * load
```

- `fit` is the cosine similarity, 0 to 1.
- `cited` is 1 if any of their work was cited, else 0.
- `reliability` is the credit score, 0 to 1.
- `load` is recent invites divided by 3, capped at 1. Three invites in the last 30 days means the full penalty.

The weights are a dataclass (`RankingWeights`) so product can retune them without a code change. Every score comes with a `reasons` list built from the same numbers, so the explanation can never drift from the ranking.

### How reliability is computed

`workflow/reliability.py`. Three smoothed rates:

```
accept   = (accepted + 0.60 * 3) / (invited   + 3)
on_time  = (on_time  + 0.75 * 3) / (completed + 3)
rating   = (rating_sum + 3.5 * 3) / (rating_count + 3) / 5
score    = 0.35 * accept + 0.40 * on_time + 0.25 * rating
```

The `3` is the prior strength: "act as if we've already seen three average outcomes". A fresh reviewer scores 0.69. Ten perfect reviews take you to about 0.97. Ten no-shows take you to about 0.25.

### How the ledger stays honest

`payments/ledger.py`. Four rules:

1. **Integers only.** Amounts are in pence. `15000` means £150.00. Floats are rejected with a `TypeError` because `0.1 + 0.2 != 0.3` is not a thing you want in a bank.
2. **Every transaction balances.** A transaction is a list of legs, each `(account, amount)`. Positive means the account gains, negative means it loses. If the legs do not sum to exactly zero, `UnbalancedTransaction` is raised and nothing is written.
3. **Append only.** Nothing is ever edited or deleted. A mistake is corrected by posting the opposite transaction.
4. **Idempotency keys.** Every transaction has a key like `release:inv_42`. Posting the same key twice returns `None` and does nothing. So if the "pay the reviewer" request is sent twice (a retry, a double click, a crash mid-way), the reviewer is paid once.

`ledger.total()` sums every balance. It is always zero. If it is ever not zero, something has bypassed the ledger, and that is the bug to find.

### How the cut is taken

`payments/pricing.py: FeePolicy.split`. Rate is in basis points (1250 = 12.5%) to stay in integers. Cut is `gross * rate // 10000`, so it rounds *down*, in the reviewer's favour. An optional minimum cut covers processing costs on tiny honoraria, capped so we never take more than exists.

```
£150.00 gross  ->  £18.75 platform  +  £131.25 reviewer
```

### How the workflow triggers money

`workflow/invitations.py: InvitationService`. Each transition method does three things in a fixed order: check the move is legal (`Invitation._go`), update the reviewer's stats, then call the matching payment flow. The payment flow uses the invitation id as its idempotency key, so even if `approve` were somehow called twice, the ledger would ignore the second release.

`expire_overdue(now)` is the janitor: it sweeps invitations that were never answered (no money involved) and accepted reviews that are more than two weeks past due (refunds the escrow).

---

## Level 4: seeing it run

`python demo.py` walks one manuscript through everything:

```
Stage 1 cast a net of 200 candidates; stage 2 removed 10:
  - p238   co-authored with Person p236 in 2025, same institution as Person p236, supervisor/student relationship with Person p236
  - p236   is an author of the manuscript
  - p276   same institution as Person p236

Stage 3 ranked the survivors:
  1. p214   score=0.667  [field 8]  topic fit 0.69; cited in manuscript (1 work(s)); reliability 0.69
  2. p219   score=0.664  [ideal]    topic fit 0.69; cited in manuscript (1 work(s)); reliability 0.69
  ...

  accepted  -> publisher   85000  escrow  15000
  approved  -> reviewer    13125  platform  1875  escrow 0
  ledger total (must be 0): 0

Ledger:
  deposit:topup-1  external-100000  publisher:pub+100000
  hold:inv_1       publisher:pub-15000  escrow:inv_1+15000
  release:inv_1    escrow:inv_1-15000  reviewer:p214+13125  platform:revenue+1875
```

Notice the number one pick is tagged `[field 8]`, not `[ideal]`. That is an interdisciplinary researcher from a neighbouring field who published in this one and got cited. The benchmark counts that as a miss; an editor might not. That tension is the most interesting open question in the ranking, and it is documented in `docs/ASSESSMENT.md`.

### How the evaluation knows the right answer

`eval/synth.py` builds a fake world where the truth is known by construction: 12 fields, each with a vocabulary; 72 labs of 4 people, each lab in one field at one institution; papers written by lab-mates using their field's words; manuscripts written by a lab, citing their field's papers. So for any manuscript, "ideal reviewer" is well-defined: same field, not in the authors' lab or institution. `eval/run_eval.py` then asks: of the top five recommended, how many are ideal? Did any conflicted person slip through? Is the invite load spread fairly? Does the money add up after 450 randomised lifecycles?

Difficulty is turned up by shrinking the word pool (so fields share more vocabulary), lowering the share of topic words per abstract, and adding interdisciplinary people. Precision@5 goes 1.00, 0.98, 0.91, 0.81 across the four levels; conflict leaks stay at zero on all of them.

---

## What is real and what is a stand-in

| Component | In the prototype | In production |
|---|---|---|
| Text fingerprint | TF-IDF bag of words | SPECTER2 or similar scientific embedding, same interface |
| Nearest neighbour search | linear scan (6 ms per 288 reviewers) | pgvector / FAISS index |
| Publication data | synthetic | OpenAlex API, refreshed nightly |
| Identity | string ids | ORCID OAuth |
| Institution / advisor / grant | synthetic, complete | ORCID (patchy) plus self-declaration |
| Ledger | in-memory Python | Postgres table with the same four rules, or a ledger service |
| Payout | `withdraw` to `external` | Stripe Connect or Wise; the ledger entry stays identical |
| Time | injected `datetime` | the clock, plus a scheduled job for `expire_overdue` |

Every seam is a function boundary that already exists. Nothing needs to be redesigned to go real; things need to be swapped.

*Tags: reviewmatch, guide, architecture, cit_rep*
