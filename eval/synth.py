"""Generate a fake academic world with ground truth.

Why synthetic? Because with real data we would never know who the *right* reviewer was.
Here we do: every person belongs to a field, every manuscript comes from a field, so
"ideal reviewer" is well-defined and the matcher can be scored rather than eyeballed.

Structure of the world:
  fields         F topics. Each has a vocabulary of `field_vocab` words. Adjacent fields
                 share `overlap` words so the matcher must cope with fuzzy boundaries.
  institutions   I universities.
  labs           groups of `lab_size` people at one institution, all in one field.
                 Lab mates co-author, share grants, and one is the others' advisor.
  works          each person writes several papers with 1-2 lab mates.
  manuscripts    written by 1-3 members of one lab; cites works from its field.

Ground truth for a manuscript:
  ideal      reviewers in the same field who are NOT in the authors' lab or institution
  conflicted reviewers in the authors' lab (coauthor/advisor/grant) or institution
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date

from reviewmatch.domain.models import Journal, Manuscript, Person, ReviewerProfile, Work

GENERIC = """data analysis model framework evaluation performance system experimental
theory application design measurement comparison technique implementation observation
sample parameter estimate significant effect variable condition process structure
function dynamic property behaviour distribution correlation baseline benchmark""".split()


@dataclass
class World:
    seed: int
    today: date
    people: dict[str, Person]
    works: dict[str, Work]
    reviewers: dict[str, ReviewerProfile]
    journals: dict[str, Journal]
    manuscripts: list[Manuscript]
    field_of: dict[str, int]                 # person id -> field
    lab_of: dict[str, int]                   # person id -> lab
    manuscript_field: dict[str, int]
    fields_vocab: list[list[str]] = field(default_factory=list)

    def ideal_reviewers(self, m: Manuscript) -> set[str]:
        f = self.manuscript_field[m.id]
        author_labs = {self.lab_of[a] for a in m.author_ids}
        author_insts = {self.people[a].institution_id for a in m.author_ids}
        return {rid for rid in self.reviewers
                if self.field_of[rid] == f
                and self.lab_of[rid] not in author_labs
                and self.people[rid].institution_id not in author_insts}

    def truly_conflicted(self, m: Manuscript) -> set[str]:
        author_labs = {self.lab_of[a] for a in m.author_ids}
        author_insts = {self.people[a].institution_id for a in m.author_ids}
        return {rid for rid in self.reviewers
                if self.lab_of[rid] in author_labs
                or self.people[rid].institution_id in author_insts}


def _make_vocab(rng: random.Random, n_fields: int, size: int, pool_size: int) -> list[list[str]]:
    """Each field samples `size` words from a shared pool of `pool_size` words.

    Smaller pool = more words shared between fields = harder to tell fields apart.
    With pool_size == n_fields * size the fields are disjoint (easy); with pool_size == 2*size
    every pair of fields shares roughly half its vocabulary (hard).
    """
    pool = [f"term{i}" for i in range(pool_size)]
    return [rng.sample(pool, size) for _ in range(n_fields)]


def _abstract(rng: random.Random, vocab: list[str], n_words: int = 60, topic_share: float = 0.5) -> str:
    words = [rng.choice(vocab) if rng.random() < topic_share else rng.choice(GENERIC) for _ in range(n_words)]
    return " ".join(words)


def build_world(seed: int = 7, n_fields: int = 12, n_institutions: int = 25, lab_size: int = 4,
                labs_per_field: int = 6, works_per_person: tuple[int, int] = (3, 7),
                n_manuscripts: int = 150, field_vocab: int = 30, pool_size: int = 120,
                topic_share: float = 0.5, interdisciplinary: float = 0.2,
                honorarium: int = 15_000) -> World:
    """`interdisciplinary` is the share of people who also publish in a second field.
    Their primary field is still the ground truth, so recommending them for their
    secondary field counts as a miss. This makes the benchmark conservative."""
    rng = random.Random(seed)
    today = date(2026, 9, 29)
    vocab = _make_vocab(rng, n_fields, field_vocab, pool_size)

    people: dict[str, Person] = {}
    field_of: dict[str, int] = {}
    lab_of: dict[str, int] = {}
    labs: list[list[str]] = []

    lab_id = 0
    for f in range(n_fields):
        for _ in range(labs_per_field):
            inst = f"inst_{rng.randrange(n_institutions)}"
            grant = f"grant_{lab_id}"
            members = []
            for k in range(lab_size):
                pid = f"p{len(people)}"
                members.append(pid)
                people[pid] = Person(pid, f"Person {pid}", orcid=f"0000-{pid}", institution_id=inst,
                                     grant_ids=frozenset({grant}) if rng.random() < 0.6 else frozenset())
                field_of[pid] = f
                lab_of[pid] = lab_id
            head = members[0]
            for pid in members[1:]:
                people[pid].advisor_id = head
            labs.append(members)
            lab_id += 1

    second_field = {pid: rng.randrange(n_fields) for pid in people if rng.random() < interdisciplinary}

    works: dict[str, Work] = {}
    works_by_field: dict[int, list[str]] = {f: [] for f in range(n_fields)}
    for lab in labs:
        f = field_of[lab[0]]
        for pid in lab:
            for _ in range(rng.randint(*works_per_person)):
                wf = second_field[pid] if pid in second_field and rng.random() < 0.5 else f
                coauthors = tuple(dict.fromkeys([pid] + rng.sample(lab, rng.randint(0, 2))))
                wid = f"w{len(works)}"
                works[wid] = Work(wid, _abstract(rng, vocab[wf], 8, topic_share), _abstract(rng, vocab[wf], 60, topic_share),
                                  coauthors, year=rng.randint(today.year - 12, today.year))
                works_by_field[wf].append(wid)

    reviewers = {pid: ReviewerProfile(p) for pid, p in people.items()}
    journals = {"j": Journal("j", "Journal of Synthetic Studies", "pub", honorarium_minor=honorarium)}

    manuscripts: list[Manuscript] = []
    manuscript_field: dict[str, int] = {}
    for i in range(n_manuscripts):
        lab = rng.choice(labs)
        f = field_of[lab[0]]
        authors = tuple(rng.sample(lab, rng.randint(1, 3)))
        refs = tuple(rng.sample(works_by_field[f], min(6, len(works_by_field[f]))))
        mid = f"m{i}"
        manuscripts.append(Manuscript(mid, _abstract(rng, vocab[f], 8, topic_share),
                                      _abstract(rng, vocab[f], 60, topic_share), authors, "j", refs))
        manuscript_field[mid] = f

    return World(seed, today, people, works, reviewers, journals, manuscripts,
                 field_of, lab_of, manuscript_field, vocab)
