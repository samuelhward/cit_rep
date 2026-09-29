# Assessment: how well does the prototype work?

Source of numbers: `eval/REPORT.md` (regenerate with `python eval/run_eval.py`). Unit tests: `python -m pytest` (29 tests).

## Headline

| Subsystem | Verdict | Evidence |
|---|---|---|
| Conflict filter | **Works, and matters** | 0 leaks across 600 matches on four difficulty levels. Turning it off produces 158 leaks and drops precision@5 from 0.91 to 0.75. |
| Matching (topic fit) | **Works, degrades gracefully** | precision@5 goes 1.00, 0.98, 0.91, 0.81 as fields get harder to tell apart. Random baseline is 0.07 throughout. |
| Load balancing | **Works** | Gini 0.44 without, 0.29 with. Max invites to any one reviewer 6 down to 4. 25 more reviewers used. |
| Payments ledger | **Works** | 565 transactions, ledger sums to zero, no escrow left open, platform revenue exactly equals the sum of computed cuts, a second "release" call is a no-op. |
| Workflow state machine | **Works** | All illegal transitions raise; every legal one moves money exactly once. |
| Reliability signal | **Untested by the eval** | Every synthetic reviewer starts with identical stats, so the signal has zero effect in the benchmark. Unit tests confirm the score moves the right way; the benchmark does not exercise it. |

## Where it is weaker than the table suggests

**1. The benchmark is still easier than reality.**
Synthetic abstracts are bags of words drawn from a field vocabulary. Real abstracts use synonyms, jargon that shifts between subfields, and words that mean different things in different fields. TF-IDF cannot see that "attention" in neuroscience and "attention" in machine learning are different topics. The "brutal" world (0.81) is probably the closest to real life, and a real embedding model would be needed to hold that number on real data.

**2. The citation bonus is double-edged.**
On the hard world, removing the citation bonus *raises* precision@5 (0.91 to 0.96) while slightly lowering hit@1. The demo shows why: an interdisciplinary researcher from a neighbouring field who published in the manuscript's field and got cited jumps to number one. By the benchmark's conservative ground truth that is a miss. By an editor's judgement it is probably a fine reviewer. Decision needed: keep the bonus but lower its weight, or make "cited" a tie-breaker rather than a scoring term. It should not be tuned on this benchmark alone.

**3. Matching is a linear scan.**
About 6 ms per match over 288 reviewers. That is a full comparison against every reviewer. At 100k reviewers it is roughly 2 seconds per match in pure Python, which is tolerable for an editor clicking a button but not for batch re-matching. The seam is `ReviewerIndex.generate`: swap the loop for an approximate nearest-neighbour index (pgvector, FAISS) and it scales.

**4. Conflict detection is only as good as the graph.**
The filter catches co-authorship, institution, advisor and grant links because the synthetic world records them. In production: co-authorship comes from OpenAlex and is good; institution comes from ORCID and is patchy; advisor and grant links mostly do not exist in any public dataset. Expect to lean on reviewer self-declaration for those two.

**5. Reliability has a cold-start bias built in.**
New reviewers start at the prior (about 0.69). A reviewer who has done 10 perfect reviews scores about 0.97. That gap is intentional but means established reviewers are favoured, which pulls against load balancing. The weights are exposed in `RankingWeights` and `reliability.py` so this trade-off is tunable, but nobody has tuned it.

**6. Money is correct but naive.**
No currencies, no VAT, no payout provider, no tax reporting, no dispute state. The ledger design survives all of those additions (they are more accounts and more transaction types), but none are built.

## What I would do next, in order

1. Replace synthetic text with a real corpus sample (OpenAlex dump for one field) and re-run the eval with human-labelled "good reviewer" judgements for 50 manuscripts. This is the only way to know if 0.81 is optimistic.
2. Swap TF-IDF for SPECTER2 embeddings behind the same `Vectorizer` interface and compare on that corpus.
3. Decide the citation-bonus policy with an editor in the room.
4. Add a `disputed` state to the invitation machine so a rejected review can be appealed without inventing money movements.

*Tags: reviewmatch, assessment, eval, cit_rep*
