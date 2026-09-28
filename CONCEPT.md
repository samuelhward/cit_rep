# Peer Review Marketplace — Concept Draft

**Working name:** ReviewMatch (placeholder)
**One-liner:** A two-sided marketplace that matches manuscripts with qualified, available, conflict-free academic reviewers in minutes instead of weeks.

> Note: the brief was cut off at "automate the reviewer finding process, as well as…". This draft assumes the second aim is *speeding up and incentivising the review itself*. Adjust if that's wrong.

---

## 1. The problem (simple version)

Peer review is a job with no job board.

- **Editors** spend hours hand-picking reviewers from memory, Google Scholar, and reference lists. Acceptance rates are ~30-40%, so they invite 3x more than they need. Median time to find two willing reviewers: 2-4 weeks.
- **Academics** get review requests randomly, often off-topic, always unpaid, with zero credit that counts for tenure.
- **Publishers** eat the cost: slow turnaround, unhappy authors, editors burning out.

Analogy: it's like hiring contractors by cold-calling everyone in the phone book whose surname sounds like "plumber". A marketplace replaces cold-calling with a searchable, verified, rated pool.

## 2. Who's on each side

| Side | Who | What they want |
|---|---|---|
| **Demand** | Journal editors, editorial assistants, publisher platforms (Elsevier, Springer Nature, Wiley, society journals, OA megajournals) | Fast, qualified, conflict-free reviewers who actually deliver |
| **Supply** | Academics, postdocs, senior PhDs, industry researchers | Relevant requests, recognition, optionally payment, control over workload |

## 3. How it works

### Publisher flow
1. Editor pastes a manuscript (or connects via API from their submission system, e.g. Editorial Manager / ScholarOne).
2. System extracts topic fingerprint (title, abstract, keywords, references).
3. Returns a ranked shortlist of reviewers with: fit score, availability, past reliability, COI flags.
4. Editor clicks "invite". Reviewer accepts/declines in-app. Deadline and reminders are automatic.
5. Review submitted through the platform (or handed back to the publisher's system).

### Reviewer flow
1. Sign up with **ORCID** (one click, verified identity, publication history auto-imported).
2. Set preferences: topics, max reviews/month, blackout dates, paid vs. unpaid, journals to avoid.
3. Receive only relevant invites. Accept/decline in one tap.
4. Build a verified review record (counts, timeliness, editor ratings) exportable to CV / tenure dossier.

## 4. The matching engine (the actual product)

Layered like a funnel:

1. **Candidate generation** — embed the manuscript abstract; nearest-neighbour search against embeddings of every reviewer's publications (from OpenAlex / Semantic Scholar). Also pull authors cited in the manuscript's references.
2. **Hard filters** — conflict of interest: co-authored with any author in last 5 years, same institution, same funding grant, recent PhD advisor/student. Built from the co-authorship graph. Also: reviewer is opted out, over capacity, or on blackout.
3. **Ranking** — weighted score of topical fit, seniority appropriate to venue, past acceptance rate, on-time delivery rate, editor quality ratings, and *load-balancing* (down-rank people who've been asked recently to spread demand and avoid the "same 20 reviewers" problem).
4. **Explainability** — every recommendation shows *why*: "3 papers on X, cited in refs 12 and 40, no COI detected, 92% on-time".

Level-up view: this is a recommender system with a hard constraint layer. Think dating app for manuscripts, except the constraint checking is the moat, not the swiping.

## 5. Incentives (the second half of the brief)

Reviewer finding is only half the delay. The other half is reviewers sitting on it. Levers:

- **Recognition** — verified, DOI-stamped review credits (like Publons / Web of Science Reviewer Recognition), plus annual certificates and a public profile.
- **Payment (optional, publisher-set)** — flat honorarium per review (e.g. £100-300) or APC-funded credits. Some publishers already do this; the platform handles escrow and payout. Reviewers can route fees to a charity or their lab.
- **Reciprocity credits** — review one, jump the queue when you submit. Works best for society journals and megajournals.
- **Speed nudges** — shorter default deadlines with structured review templates (10-minute triage vs. full review), progress bars, automatic reminders, and reliability scores that reward on-time delivery.

## 6. Trust and ethics (where this can die)

- **Identity** — ORCID login mandatory. No anonymous or unverifiable reviewers; this kills fake-reviewer fraud.
- **COI** — automated graph check, plus mandatory self-declaration.
- **Anonymity** — supports single-blind, double-blind, and open review; reviewer identity never leaked to authors unless policy allows.
- **Confidentiality** — manuscripts encrypted, expiring access, no training on manuscript content.
- **Pay-for-review controversy** — keep payment opt-in per journal and transparent; never let fees influence the *outcome* of a review (platform sees timeliness, never recommendation).
- **Bias** — monitor and report gender/geography distribution of invites; load-balancing helps here too.

## 7. Business model

| Model | Who pays | Notes |
|---|---|---|
| **SaaS per journal** (primary) | Publisher | Tiered by manuscript volume. Predictable, sells to procurement. |
| **Per-match fee** | Publisher | Pay only for completed reviews; good for small journals and pilots. |
| **Payment rails cut** | Publisher | 10-15% on any honoraria flowing through the platform. |
| **API licensing** | Submission-system vendors | Embed the matcher into Editorial Manager etc. |

Reviewers never pay. Ever.

## 8. Competitive landscape

- **Clarivate Reviewer Locator / Elsevier Find Reviewers** — built into publisher stacks, but closed, no availability data, no incentives layer.
- **Prophy, Reviewer Finder (various)** — good matching, no marketplace (reviewer isn't a participant, just a name in a database).
- **Publons (now Web of Science Reviewer Recognition)** — recognition only, no matching.
- **Reviewer Credits, ReviewerHub** — small, mostly recognition/payment.

Gap: nobody combines *matching + verified availability + incentives + COI* in one loop where the reviewer is a first-class user.

## 9. MVP (12 weeks, one small team)

**In scope**
- ORCID sign-up, reviewer profile with auto-imported publications
- Manuscript upload → ranked shortlist with COI flags and explanations
- Invite / accept / decline / deadline tracking
- Editor dashboard, reviewer dashboard
- Basic reliability score

**Out of scope for MVP**
- Payments, submission-system integrations, open review, reciprocity credits

**Validation target:** 3-5 society or OA journals, 500 verified reviewers in one field (pick one, e.g. neuroscience or computer science, where OpenAlex coverage is dense). Success = median time-to-two-accepted-reviewers under 5 days.

## 10. Tech sketch

- **Data:** OpenAlex (free, complete-ish), Crossref, ORCID API, Semantic Scholar embeddings (SPECTER2)
- **Matching:** vector DB (pgvector is enough at MVP scale), co-authorship graph in Postgres, LLM only for explanations and topic summaries
- **Stack:** Next.js + Postgres + a Python matching service; ORCID OAuth; manuscripts in object storage with signed, expiring URLs
- **Integrations later:** Editorial Manager, ScholarOne, OJS (open source, easiest first)

## 11. Biggest risks

1. **Cold start** — need reviewers before publishers care and vice versa. Mitigation: seed supply from OpenAlex (passive profiles reviewers can claim), sell to one field first.
2. **Publisher inertia** — long procurement cycles. Mitigation: start with society journals and OJS-based journals; sell per-match, not annual licences.
3. **Reviewer fatigue is structural** — a marketplace can't fix the economics of unpaid labour alone. Payment/reciprocity is where real differentiation lives.
4. **Data quality** — name disambiguation and COI graph errors erode trust fast. ORCID-only mitigates most of it.

## 12. Open questions

- Is payment core or optional? (Changes the go-to-market and the ethics posture.)
- Marketplace (reviewer opts in) vs. tool (editor searches a database)? This draft assumes marketplace.
- Single field first, or horizontal from day one?
- Which submission system to integrate first? OJS is easiest, Editorial Manager has the most volume.

---
*Tags: peer-review, marketplace, concept, cit_rep, scholarly-publishing*
