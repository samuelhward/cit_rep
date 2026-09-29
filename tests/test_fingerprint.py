from reviewmatch.matching.fingerprint import Vectorizer, cosine, tokenize


def test_tokenize_drops_stopwords_and_short_tokens():
    assert tokenize("The results of a CRISPR study on mice") == ["crispr", "mice"]


def test_similar_texts_score_higher_than_unrelated():
    v = Vectorizer().fit([
        "graph neural networks for molecule property prediction",
        "transformer language models for summarisation",
        "molecular dynamics simulation of proteins",
    ])
    a = v.vectorize("graph neural network molecule prediction")
    b = v.vectorize("graph networks predicting molecule properties")
    c = v.vectorize("language model summarisation transformer")
    assert cosine(a, b) > cosine(a, c)


def test_idf_downweights_common_words():
    v = Vectorizer().fit(["common rare1", "common rare2", "common rare3"])
    assert v.idf["common"] < v.idf["rare1"]


def test_cosine_of_empty_is_zero():
    assert cosine({}, {"a": 1.0}) == 0.0
