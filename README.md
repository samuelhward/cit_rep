# cit_rep / ReviewMatch

Prototype engine for a peer-review marketplace: match manuscripts to qualified, conflict-free reviewers, and pay reviewers with a platform cut.

- `CONCEPT.md` — the product concept
- `SCOPE.md` — technical scope of this prototype
- `docs/GUIDE.md` — **start here**: an intuitive walkthrough of how everything works
- `docs/ASSESSMENT.md` — how well it works, and where it doesn't
- `docs/SECURITY.md` — what data we hold, what we outsource, what we must do ourselves
- `eval/REPORT.md` — generated metrics

## Run it

```
pip install pytest
python -m pytest            # 29 unit tests
python demo.py              # one manuscript through matching and payment
python eval/run_eval.py     # full benchmark, writes eval/REPORT.md (~12s)
```

Stdlib only. Python 3.11+.

*Tags: reviewmatch, cit_rep*
