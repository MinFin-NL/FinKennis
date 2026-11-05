import uuid

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import Chunk, Inzicht
from app.rag.ingest_worker import (
    MAX_POGINGEN,
    claim_next,
    claim_next_inzichten,
    process,
    process_inzichten,
    requeue_stuck,
)
from app.rag.inzichten import Fragment, secties
from tests.test_api import DOC, _sse_events

VERGOEDING = {
    "thema": "Thuiswerkvergoeding",
    "tekst": "Thuiswerkers krijgen 2,40 euro per dag.",
    "soort": "cijfer",
    "belang": 3,
    "fragmenten": [1],
}


def _vergoeding_als_die_erin_staat(sectie: str) -> list[dict]:
    return [VERGOEDING] if "2,40" in sectie else []


async def _verwerk_alles(fake_ollama, fake_chat):
    settings = get_settings()
    while doc := await claim_next(SessionLocal):
        await process(doc, SessionLocal, fake_ollama, settings)
    while doc := await claim_next_inzichten(SessionLocal):
        await process_inzichten(doc, SessionLocal, fake_ollama, fake_chat.model, settings)


async def _kennisbank_met_doc(client, naam="HR"):
    kb = (await client.post("/api/v1/kennisbanken", json={"naam": naam})).json()
    url = f"/api/v1/kennisbanken/{kb['id']}/documenten"
    await client.post(url, files=[("bestanden", ("thuiswerken.md", DOC, "text/markdown"))])
    return kb, url


def _fragment(tekst: str, kopje: str) -> Fragment:
    return Fragment(uuid.uuid4(), tekst, [kopje], None)


def test_secties_blijven_onder_het_budget_en_volgen_hoofdstukken():
    a = [_fragment("woord " * 30, "H1") for _ in range(3)]  # ~39 tokens per fragment
    b = [_fragment("woord " * 30, "H2") for _ in range(2)]

    # Ruim budget: wisselt het hoofdstuk na een halfvolle sectie, dan begint er een nieuwe.
    assert [len(s) for s in secties(a + b, 200)] == [3, 2]
    # Krap budget: hooguit twee fragmenten per sectie. Een kort restje van een hoofdstuk
    # gaat mee met het volgende in plaats van een eigen, bijna lege sectie te worden.
    assert [len(s) for s in secties(a + b, 80)] == [2, 2, 1]
    # Eén fragment groter dan het budget komt toch mee, in een eigen sectie.
    assert [len(s) for s in secties([_fragment("woord " * 300, "H1")], 80)] == [1]


async def test_inzichten_worden_na_het_verwerken_gemaakt(client, fake_ollama, fake_chat):
    fake_chat.bevindingen = _vergoeding_als_die_erin_staat
    _, url = await _kennisbank_met_doc(client)

    await _verwerk_alles(fake_ollama, fake_chat)

    doc = (await client.get(url)).json()[0]
    assert doc["inzichtenStatus"] == "gereed", doc["inzichtenFoutmelding"]
    assert doc["aantalInzichten"] == 1
    # Het hele document is gelezen, niet alleen een paar zoekresultaten.
    assert "Vergoeding" in "".join(fake_chat.secties)
    assert "Apparatuur" in "".join(fake_chat.secties)
    async with SessionLocal() as s:
        inzicht = await s.scalar(select(Inzicht))
        bron = await s.get(Chunk, inzicht.chunk_ids[0])
    assert inzicht.tekst == VERGOEDING["tekst"]
    assert "2,40" in bron.tekst


async def test_bevinding_zonder_geldig_fragment_vervalt(client, fake_ollama, fake_chat):
    fake_chat.bevindingen = lambda sectie: [
        {**VERGOEDING, "fragmenten": [99]},
        {**VERGOEDING, "tekst": "Te belangrijk", "belang": 7},
    ]
    _, url = await _kennisbank_met_doc(client)

    await _verwerk_alles(fake_ollama, fake_chat)

    async with SessionLocal() as s:
        inzichten = (await s.scalars(select(Inzicht))).all()
    assert [i.tekst for i in inzichten] == ["Te belangrijk"] * len(fake_chat.secties)
    assert {i.belang for i in inzichten} == {3}


async def test_meerdere_secties_worden_samengevoegd(client, fake_ollama, fake_chat, monkeypatch):
    monkeypatch.setattr(get_settings(), "inzichten_sectie_tokens", 1)
    fake_chat.bevindingen = lambda sectie: [{**VERGOEDING, "tekst": "Bevinding"}]
    fake_chat.samenvoegen = lambda lijst: [
        {"thema": "Alles", "tekst": "Samen", "soort": "overig", "belang": 2, "bevindingen": [1, 2]},
        {
            "thema": "Fout",
            "tekst": "Verzonnen",
            "soort": "overig",
            "belang": 3,
            "bevindingen": [42],
        },
    ]
    _, url = await _kennisbank_met_doc(client)

    await _verwerk_alles(fake_ollama, fake_chat)

    assert len(fake_chat.secties) >= 2
    assert "[2]" in fake_chat.samenvoegprompt
    async with SessionLocal() as s:
        inzichten = (await s.scalars(select(Inzicht))).all()
    # Het samengevoegde inzicht steunt op de fragmenten van beide bevindingen; het inzicht
    # dat naar een niet-bestaande bevinding verwijst, vervalt.
    assert [i.tekst for i in inzichten] == ["Samen"]
    assert len(inzichten[0].chunk_ids) == 2


async def test_vragen_in_inzichtenmodus(client, fake_ollama, fake_chat):
    fake_chat.bevindingen = _vergoeding_als_die_erin_staat
    kb, _ = await _kennisbank_met_doc(client)
    await _verwerk_alles(fake_ollama, fake_chat)

    gesprek = (await client.post(f"/api/v1/kennisbanken/{kb['id']}/gesprekken", json={})).json()
    r = await client.post(
        f"/api/v1/gesprekken/{gesprek['id']}/berichten",
        json={"inhoud": "Wat valt op?", "modus": "inzichten"},
    )
    events = _sse_events(r.text)

    assert events[0][0] == "bronnen"
    assert "2,40" in events[0][1][0]["fragment"]
    prompt = fake_chat.laatste_berichten[-1]["content"]
    assert prompt.startswith("Inzichten:")
    assert "[1] Thuiswerkvergoeding (cijfer, belang 3) — thuiswerken.md" in prompt
    assert events[-1][0] == "klaar"
    detail = (await client.get(f"/api/v1/gesprekken/{gesprek['id']}")).json()
    assert [b["modus"] for b in detail["berichten"]] == ["inzichten", "inzichten"]


async def test_inzichtenmodus_zonder_inzichten_meldt_dat_ze_nog_komen(
    client, fake_ollama, fake_chat
):
    kb, _ = await _kennisbank_met_doc(client)
    while doc := await claim_next(SessionLocal):
        await process(doc, SessionLocal, fake_ollama, get_settings())

    gesprek = (await client.post(f"/api/v1/kennisbanken/{kb['id']}/gesprekken", json={})).json()
    r = await client.post(
        f"/api/v1/gesprekken/{gesprek['id']}/berichten",
        json={"inhoud": "Wat valt op?", "modus": "inzichten"},
    )
    events = _sse_events(r.text)

    assert events[0] == ("bronnen", [])
    assert "worden nog gemaakt" in events[1][1]
    # Zonder inzichten wordt het model niet gevraagd te gissen.
    assert fake_chat.laatste_berichten is None


async def test_gewone_vraag_vindt_fragment_via_inzicht(client, fake_ollama, fake_chat):
    fake_chat.bevindingen = _vergoeding_als_die_erin_staat
    kb, _ = await _kennisbank_met_doc(client)
    await _verwerk_alles(fake_ollama, fake_chat)

    gesprek = (await client.post(f"/api/v1/kennisbanken/{kb['id']}/gesprekken", json={})).json()
    r = await client.post(
        f"/api/v1/gesprekken/{gesprek['id']}/berichten",
        json={"inhoud": "Thuiswerkers krijgen per dag?"},
    )
    bronnen = _sse_events(r.text)[0][1]
    assert "2,40" in bronnen[0]["fragment"]


async def test_mislukte_inzichten_worden_opnieuw_geprobeerd(client, fake_ollama, fake_chat):
    def kapot(sectie):
        raise RuntimeError("rate limit")

    fake_chat.bevindingen = kapot
    _, url = await _kennisbank_met_doc(client)
    while doc := await claim_next(SessionLocal):
        await process(doc, SessionLocal, fake_ollama, get_settings())

    for _ in range(MAX_POGINGEN - 1):
        doc = await claim_next_inzichten(SessionLocal)
        await process_inzichten(doc, SessionLocal, fake_ollama, fake_chat.model, get_settings())
        assert (await client.get(url)).json()[0]["inzichtenStatus"] == "wachtrij"

    doc = await claim_next_inzichten(SessionLocal)
    await process_inzichten(doc, SessionLocal, fake_ollama, fake_chat.model, get_settings())
    doc = (await client.get(url)).json()[0]
    assert doc["inzichtenStatus"] == "fout"
    assert "rate limit" in doc["inzichtenFoutmelding"]
    # Het document zelf blijft gewoon doorzoekbaar.
    assert doc["status"] == "gereed"


async def test_afgebroken_inzichten_gaan_na_herstart_terug_in_de_wachtrij(
    client, fake_ollama, fake_chat
):
    _, url = await _kennisbank_met_doc(client)
    while doc := await claim_next(SessionLocal):
        await process(doc, SessionLocal, fake_ollama, get_settings())

    assert await claim_next_inzichten(SessionLocal)
    await requeue_stuck(SessionLocal)
    assert (await client.get(url)).json()[0]["inzichtenStatus"] == "wachtrij"


async def test_inzichten_van_een_document_bekijken(client, fake_ollama, fake_chat):
    fake_chat.bevindingen = _vergoeding_als_die_erin_staat
    _, url = await _kennisbank_met_doc(client)
    await _verwerk_alles(fake_ollama, fake_chat)
    doc = (await client.get(url)).json()[0]

    r = await client.get(f"{url}/{doc['id']}/inzichten")

    assert r.status_code == 200
    [inzicht] = r.json()
    assert inzicht["thema"] == "Thuiswerkvergoeding"
    assert "2,40" in inzicht["bronnen"][0]["fragment"]
    assert (await client.get(f"{url}/{uuid.uuid4()}/inzichten")).status_code == 404


async def test_inzichten_opnieuw_maken(client, fake_ollama, fake_chat):
    _, url = await _kennisbank_met_doc(client)
    doc = (await client.get(url)).json()[0]
    # Nog niet verwerkt: eerst het document zelf.
    assert (await client.post(f"{url}/{doc['id']}/inzichten")).status_code == 409

    fake_chat.bevindingen = lambda sectie: 1 / 0
    while d := await claim_next(SessionLocal):
        await process(d, SessionLocal, fake_ollama, get_settings())
    for _ in range(MAX_POGINGEN):
        d = await claim_next_inzichten(SessionLocal)
        await process_inzichten(d, SessionLocal, fake_ollama, fake_chat.model, get_settings())
    assert (await client.get(url)).json()[0]["inzichtenStatus"] == "fout"

    r = await client.post(f"{url}/{doc['id']}/inzichten")
    assert r.status_code == 202
    assert r.json()["inzichtenStatus"] == "wachtrij"
    assert r.json()["inzichtenFoutmelding"] is None

    fake_chat.bevindingen = _vergoeding_als_die_erin_staat
    await _verwerk_alles(fake_ollama, fake_chat)
    assert (await client.get(url)).json()[0]["aantalInzichten"] == 1


async def test_na_een_herstart_gaat_het_lezen_verder(client, fake_ollama, fake_chat, monkeypatch):
    monkeypatch.setattr(get_settings(), "inzichten_sectie_tokens", 1)
    # Eén sectie tegelijk, zodat de eerste klaar is voordat de tweede mislukt.
    monkeypatch.setattr(get_settings(), "inzichten_gelijktijdig", 1)
    _, url = await _kennisbank_met_doc(client)
    while d := await claim_next(SessionLocal):
        await process(d, SessionLocal, fake_ollama, get_settings())

    # De tweede sectie mislukt: de eerste is dan al gelezen en bewaard.
    def tweede_kapot(sectie):
        if len(fake_chat.secties) > 1:
            raise RuntimeError("weg")
        return [VERGOEDING]

    fake_chat.bevindingen = tweede_kapot
    d = await claim_next_inzichten(SessionLocal)
    await process_inzichten(d, SessionLocal, fake_ollama, fake_chat.model, get_settings())
    doc = (await client.get(url)).json()[0]
    assert doc["inzichtenStatus"] == "wachtrij"
    assert doc["inzichtenSectiesKlaar"] == 1
    totaal = doc["inzichtenSectiesTotaal"]
    assert totaal >= 2

    fake_chat.secties.clear()
    fake_chat.bevindingen = lambda sectie: [VERGOEDING]
    await _verwerk_alles(fake_ollama, fake_chat)

    # Alleen de nog niet gelezen secties zijn opnieuw naar het model gegaan.
    assert len(fake_chat.secties) == totaal - 1
    doc = (await client.get(url)).json()[0]
    assert doc["inzichtenStatus"] == "gereed"
    assert doc["inzichtenSectiesKlaar"] == totaal


async def test_inzichtenstatus_van_de_kennisbank(client, fake_ollama, fake_chat):
    fake_chat.bevindingen = _vergoeding_als_die_erin_staat
    kb, _ = await _kennisbank_met_doc(client)
    status_url = f"/api/v1/kennisbanken/{kb['id']}/inzichtenstatus"
    while d := await claim_next(SessionLocal):
        await process(d, SessionLocal, fake_ollama, get_settings())

    voor = (await client.get(status_url)).json()
    assert voor["aantalInzichten"] == 0
    assert voor["documentenOnderweg"] == 1

    await _verwerk_alles(fake_ollama, fake_chat)
    na = (await client.get(status_url)).json()
    assert na == {
        "aantalInzichten": 1,
        "documentenKlaar": 1,
        "documentenOnderweg": 0,
        "documentenMislukt": 0,
        "sectiesKlaar": 0,
        "sectiesTotaal": 0,
    }


async def test_samenvoegen_gaat_in_rondes(monkeypatch):
    from app.rag import inzichten as mod
    from app.rag.inzichten import NieuwInzicht

    rondes: list[int] = []

    async def nep_samenvoegen(model, bevindingen, maximum):
        rondes.append(len(bevindingen))
        return bevindingen[:maximum]

    monkeypatch.setattr(mod, "_voeg_samen", nep_samenvoegen)
    veel = [NieuwInzicht("t", f"b{i}", "overig", 2, [uuid.uuid4()]) for i in range(150)]

    uit = await mod._voeg_samen_in_rondes(None, veel, 20)

    # 150 bevindingen: drie groepen van hooguit 60, dan één laatste ronde over 60 resten.
    assert rondes == [60, 60, 30, 60]
    assert len(uit) == 20
