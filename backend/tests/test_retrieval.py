import uuid

from app.rag.retrieval import per_document_bij_elkaar, rrf, spreid_over_documenten


def test_rrf_beloont_treffers_in_beide_lijsten():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = rrf([[a, b], [c, b]])
    assert max(scores, key=scores.get) == b
    assert scores[a] == scores[c]


def test_spreiden_geeft_elk_document_een_plek_en_groepeert_per_document():
    a, b = uuid.uuid4(), uuid.uuid4()
    a1, a2, a3, b1 = (uuid.uuid4() for _ in range(4))
    document_van = {a1: a, a2: a, a3: a, b1: b}
    # Document a staat bovenaan; zonder spreiding kwam b er niet in.
    gekozen = spreid_over_documenten([a1, a2, a3, b1], document_van, limiet=3, per_document=2)
    assert gekozen == [a1, a2, b1]
    # Per document bij elkaar, ook als de beste van b tussen die van a in staat.
    gekozen = spreid_over_documenten([a1, b1, a2], document_van, limiet=3, per_document=2)
    assert gekozen == [a1, a2, b1]


def test_spreiden_vult_open_plekken_als_er_weinig_documenten_zijn():
    a = uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(4)]
    gekozen = spreid_over_documenten(ids, dict.fromkeys(ids, a), limiet=3, per_document=1)
    assert gekozen == ids[:3]


def test_per_document_bij_elkaar_houdt_de_volgorde_binnen_een_document():
    items = [("a", 1), ("b", 1), ("a", 2), ("c", 1), ("b", 2)]
    doc = {k: uuid.uuid4() for k in "abc"}
    assert per_document_bij_elkaar(items, lambda i: doc[i[0]]) == [
        ("a", 1),
        ("a", 2),
        ("b", 1),
        ("b", 2),
        ("c", 1),
    ]
