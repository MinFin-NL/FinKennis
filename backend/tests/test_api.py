import asyncio
import json

from app.config import get_settings
from app.db import SessionLocal
from app.rag.ingest_worker import claim_next, process

DOC = b"""# Thuiswerkbeleid

## Vergoeding

Medewerkers die thuiswerken ontvangen een thuiswerkvergoeding van 2,40 euro per dag.

## Apparatuur

De werkgever stelt een laptop en een beeldscherm beschikbaar.
"""


async def _verwerk_wachtrij(fake_ollama):
    while doc := await claim_next(SessionLocal):
        await process(doc, SessionLocal, fake_ollama, get_settings())


def _sse_events(body: str) -> list[tuple[str, object]]:
    events = []
    for blok in body.strip().split("\n\n"):
        regels = dict(r.split(": ", 1) for r in blok.splitlines())
        events.append((regels["event"], json.loads(regels["data"])))
    return events


async def test_kennisbank_crud(client):
    r = await client.post("/api/v1/kennisbanken", json={"naam": "HR", "omschrijving": "Beleid"})
    assert r.status_code == 201
    kb = r.json()
    assert r.headers["location"].endswith(kb["id"])
    assert r.headers["api-version"]

    r = await client.patch(f"/api/v1/kennisbanken/{kb['id']}", json={"naam": "HR-beleid"})
    assert r.json()["naam"] == "HR-beleid"

    r = await client.get("/api/v1/kennisbanken")
    assert [k["naam"] for k in r.json()] == ["HR-beleid"]

    r = await client.delete(f"/api/v1/kennisbanken/{kb['id']}")
    assert r.status_code == 204
    r = await client.get(f"/api/v1/kennisbanken/{kb['id']}")
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"


async def test_ongeldige_invoer_geeft_problem_json(client):
    r = await client.post("/api/v1/kennisbanken", json={"naam": ""})
    assert r.status_code == 422
    assert r.json()["invalidParams"][0]["name"] == "body.naam"


async def test_upload_verwerken_en_vragen(client, fake_ollama):
    kb = (await client.post("/api/v1/kennisbanken", json={"naam": "HR"})).json()
    url = f"/api/v1/kennisbanken/{kb['id']}/documenten"

    r = await client.post(url, files=[("bestanden", ("thuiswerken.md", DOC, "text/markdown"))])
    assert r.status_code == 202
    assert r.json()["toegevoegd"][0]["status"] == "wachtrij"

    # Hetzelfde bestand nog eens: wordt overgeslagen.
    r = await client.post(url, files=[("bestanden", ("kopie.md", DOC, "text/markdown"))])
    assert r.json() == {"toegevoegd": [], "overgeslagen": ["kopie.md"]}

    await _verwerk_wachtrij(fake_ollama)
    docs = (await client.get(url)).json()
    assert docs[0]["status"] == "gereed", docs[0]["foutmelding"]
    assert docs[0]["aantalChunks"] >= 1

    gesprek = (await client.post(f"/api/v1/kennisbanken/{kb['id']}/gesprekken", json={})).json()
    r = await client.post(
        f"/api/v1/gesprekken/{gesprek['id']}/berichten",
        json={"inhoud": "Hoeveel is de thuiswerkvergoeding per dag?"},
    )
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(r.text)

    assert events[0][0] == "bronnen"
    assert events[0][1][0]["bestandsnaam"] == "thuiswerken.md"
    assert "".join(d for e, d in events if e == "token") == "Het antwoord staat in [1]."
    assert events[-1][0] == "klaar"
    # De gevonden tekst is meegegeven aan het taalmodel.
    assert "2,40 euro" in fake_ollama.laatste_berichten[-1]["content"]

    detail = (await client.get(f"/api/v1/gesprekken/{gesprek['id']}")).json()
    assert detail["titel"].startswith("Hoeveel is de thuiswerkvergoeding")
    assert [b["rol"] for b in detail["berichten"]] == ["user", "assistant"]
    assert detail["berichten"][1]["bronnen"][0]["nummer"] == 1


async def test_onleesbaar_document_krijgt_status_fout(client, fake_ollama):
    kb = (await client.post("/api/v1/kennisbanken", json={"naam": "HR"})).json()
    url = f"/api/v1/kennisbanken/{kb['id']}/documenten"
    await client.post(url, files=[("bestanden", ("kapot.pdf", b"geen pdf", "application/pdf"))])

    await _verwerk_wachtrij(fake_ollama)
    doc = (await client.get(url)).json()[0]
    assert doc["status"] == "fout"
    assert doc["foutmelding"]


async def test_niet_ondersteund_bestandstype(client):
    kb = (await client.post("/api/v1/kennisbanken", json={"naam": "HR"})).json()
    r = await client.post(
        f"/api/v1/kennisbanken/{kb['id']}/documenten",
        files=[("bestanden", ("virus.exe", b"MZ", "application/octet-stream"))],
    )
    assert r.status_code == 415


async def test_zoeken_blijft_binnen_de_kennisbank(client, fake_ollama):
    a = (await client.post("/api/v1/kennisbanken", json={"naam": "A"})).json()
    b = (await client.post("/api/v1/kennisbanken", json={"naam": "B"})).json()
    await client.post(
        f"/api/v1/kennisbanken/{a['id']}/documenten",
        files=[("bestanden", ("a.md", DOC, "text/markdown"))],
    )
    await _verwerk_wachtrij(fake_ollama)

    gesprek = (await client.post(f"/api/v1/kennisbanken/{b['id']}/gesprekken", json={})).json()
    r = await client.post(
        f"/api/v1/gesprekken/{gesprek['id']}/berichten",
        json={"inhoud": "thuiswerkvergoeding"},
    )
    assert _sse_events(r.text)[0] == ("bronnen", [])
    await asyncio.sleep(0)
