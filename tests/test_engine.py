"""End-to-end: build a tiny world and check the matcher's behaviour."""
from datetime import date

from reviewmatch.domain.models import Journal, Manuscript, Person, ReviewerProfile, ReviewerStats, Work
from reviewmatch.matching import MatchConfig, Matcher

TODAY = date(2026, 9, 29)


def _world():
    people = {
        "auth": Person("auth", "Author", institution_id="u1"),
        "gnn1": Person("gnn1", "GNN Expert", institution_id="u2"),
        "gnn2": Person("gnn2", "GNN Coauthor of author", institution_id="u3"),
        "nlp": Person("nlp", "NLP Person", institution_id="u4"),
        "bio": Person("bio", "Biologist", institution_id="u5"),
    }
    works = {
        "w1": Work("w1", "Graph neural networks for molecules", "message passing molecule graph property prediction", ("gnn1",), 2024),
        "w2": Work("w2", "Graph networks for chemistry", "graph convolution molecule chemistry prediction", ("gnn2", "auth"), 2025),
        "w3": Work("w3", "Transformers for summarisation", "language model summarisation attention text", ("nlp",), 2024),
        "w4": Work("w4", "Protein folding in yeast", "protein folding yeast cell biology experiment", ("bio",), 2023),
        "w5": Work("w5", "Old graph paper", "graph molecule prediction", ("gnn1",), 2012),
    }
    reviewers = {pid: ReviewerProfile(p) for pid, p in people.items() if pid != "auth"}
    journals = {"j": Journal("j", "J", "pub", honorarium_minor=1000)}
    return people, works, reviewers, journals


def test_topical_expert_ranks_first_and_coauthor_is_excluded():
    people, works, reviewers, journals = _world()
    m = Matcher(people, works, reviewers, journals, TODAY, MatchConfig(top_k=3))
    ms = Manuscript("m", "Graph neural network molecule property prediction",
                    "we use message passing graph networks to predict molecule properties",
                    ("auth",), "j", reference_ids=("w1",))
    res = m.match(ms)
    ids = [r.reviewer.id for r in res.recommendations]
    assert ids[0] == "gnn1"
    assert "gnn2" not in ids and "coauthor" in {c.rule for c in res.excluded["gnn2"]}
    assert "cited in manuscript (1 work(s))" in res.recommendations[0].reasons


def test_load_balancing_can_reorder_close_candidates():
    people, works, reviewers, journals = _world()
    # make nlp and bio equally (ir)relevant and give gnn1 a heavy recent load
    m = Matcher(people, works, reviewers, journals, TODAY, MatchConfig(top_k=3))
    ms = Manuscript("m", "graph molecule", "graph molecule prediction", ("auth",), "j")
    base = m.match(ms).recommendations[0].reviewer.id
    loaded = m.match(ms, recent_invites={"gnn1": 10}).recommendations
    assert base == "gnn1"
    # still first on fit alone here, but score must have dropped by the full load penalty
    assert loaded[0].parts["load"] == -m.config.weights.load


def test_reliability_breaks_ties():
    people, works, reviewers, journals = _world()
    reviewers["nlp"].stats = ReviewerStats(invited=10, accepted=10, completed=10, on_time=10, rating_sum=50, rating_count=10)
    reviewers["bio"].stats = ReviewerStats(invited=10, accepted=2, completed=2, on_time=0, rating_sum=4, rating_count=2)
    m = Matcher(people, works, reviewers, journals, TODAY, MatchConfig(top_k=5, min_fit=0.0))
    ms = Manuscript("m", "unrelated topic entirely", "quantum gravity in curved spacetime", ("auth",), "j")
    ids = [r.reviewer.id for r in m.match(ms).recommendations]
    assert ids.index("nlp") < ids.index("bio")
