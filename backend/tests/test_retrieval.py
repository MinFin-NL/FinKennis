import uuid

from app.rag.retrieval import rrf


def test_rrf_beloont_treffers_in_beide_lijsten():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = rrf([[a, b], [c, b]])
    assert max(scores, key=scores.get) == b
    assert scores[a] == scores[c]
