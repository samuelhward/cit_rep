from datetime import date

from reviewmatch.domain.models import Journal, Manuscript, Person, ReviewerPreferences, ReviewerProfile, Work
from reviewmatch.matching.conflicts import CoauthorGraph, ConflictChecker

TODAY = date(2026, 9, 29)


def _world():
    people = {
        "auth": Person("auth", "Alice Author", institution_id="uni_a", advisor_id="boss", grant_ids=frozenset({"g1"})),
        "coau": Person("coau", "Carl Coauthor", institution_id="uni_b"),
        "old": Person("old", "Olga Old", institution_id="uni_c"),
        "same": Person("same", "Sam SameUni", institution_id="uni_a"),
        "boss": Person("boss", "Bea Boss", institution_id="uni_d"),
        "fund": Person("fund", "Fred Funded", institution_id="uni_e", grant_ids=frozenset({"g1"})),
        "clean": Person("clean", "Clara Clean", institution_id="uni_f"),
    }
    works = {
        "w1": Work("w1", "t", "a", ("auth", "coau"), 2024),
        "w2": Work("w2", "t", "a", ("auth", "old"), 2015),
    }
    return people, works


def _check(reviewer_id, prefs=None, journal=None, invites=0):
    people, works = _world()
    checker = ConflictChecker(people, CoauthorGraph(works), coauthor_window_years=5)
    ms = Manuscript("m", "t", "a", ("auth",), "j")
    journal = journal or Journal("j", "J", "pub", honorarium_minor=1000)
    reviewer = ReviewerProfile(people[reviewer_id], prefs or ReviewerPreferences())
    return {c.rule for c in checker.check(reviewer, ms, journal, TODAY, invites)}


def test_author_is_conflicted():
    assert _check("auth") == {"author"}


def test_recent_coauthor_is_conflicted_but_old_coauthor_is_not():
    assert "coauthor" in _check("coau")
    assert "coauthor" not in _check("old")


def test_same_institution_advisor_and_grant():
    assert "institution" in _check("same")
    assert "advisor" in _check("boss")
    assert "grant" in _check("fund")


def test_clean_reviewer_has_no_conflicts():
    assert _check("clean") == set()


def test_preferences_and_capacity():
    assert "opted_out" in _check("clean", ReviewerPreferences(excluded_journal_ids=frozenset({"j"})))
    assert "payment_pref" in _check("clean", ReviewerPreferences(accepts_paid=False))
    assert "capacity" in _check("clean", ReviewerPreferences(max_reviews_per_month=1), invites=1)
    assert "unavailable" in _check("clean", ReviewerPreferences(blackout=((date(2026, 9, 1), date(2026, 9, 30)),)))
