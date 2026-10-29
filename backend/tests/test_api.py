import asyncio
import json

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.function import FunctionModel

from app.config import get_settings
from app.db import SessionLocal
from app.rag.ingest_worker import MAX_POGINGEN, claim_next, process, requeue_stuck

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


async def test_upload_verwerken_en_vragen(client, fake_ollama, fake_chat):
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
    assert "2,40 euro" in fake_chat.laatste_berichten[-1]["content"]

    detail = (await client.get(f"/api/v1/gesprekken/{gesprek['id']}")).json()
    assert detail["titel"].startswith("Hoeveel is de thuiswerkvergoeding")
    assert [b["rol"] for b in detail["berichten"]] == ["user", "assistant"]
    assert detail["berichten"][1]["bronnen"][0]["nummer"] == 1


async def test_vervolgvraag_zoekt_met_het_onderwerp_uit_het_gesprek(client, fake_ollama, fake_chat):
    kb = (await client.post("/api/v1/kennisbanken", json={"naam": "HR"})).json()
    await client.post(
        f"/api/v1/kennisbanken/{kb['id']}/documenten",
        files=[("bestanden", ("thuiswerken.md", DOC, "text/markdown"))],
    )
    await _verwerk_wachtrij(fake_ollama)
    gesprek = (await client.post(f"/api/v1/kennisbanken/{kb['id']}/gesprekken", json={})).json()
    url = f"/api/v1/gesprekken/{gesprek['id']}/berichten"

    await client.post(url, json={"inhoud": "Krijg ik een laptop?"})
    # De eerste vraag heeft geen gesprek om te herschrijven.
    assert fake_chat.herschrijfberichten is None

    fake_chat.herschreven = "Hoeveel is de thuiswerkvergoeding per dag?"
    r = await client.post(url, json={"inhoud": "En hoeveel krijg ik daarvoor?"})
    events = _sse_events(r.text)

    herschrijfvraag = fake_chat.herschrijfberichten[-1]["content"]
    assert "Krijg ik een laptop?" in herschrijfvraag
    assert "[1]" not in herschrijfvraag
    assert events[0][1][0]["bestandsnaam"] == "thuiswerken.md"
    # Het antwoord gaat over de oorspronkelijke vraag, met het eerdere gesprek erbij.
    berichten = fake_chat.laatste_berichten
    assert berichten[-1]["content"].endswith("Vraag: En hoeveel krijg ik daarvoor?")
    gesprek_rollen = [b["role"] for b in berichten if b["role"] != "system"]
    assert gesprek_rollen == ["user", "assistant", "user"]
    assert berichten[0]["content"] == "Krijg ik een laptop?"
    assert all("[1]" not in b["content"] for b in berichten if b["role"] == "assistant")


async def test_fout_van_het_taalmodel_wordt_gemeld(client, app):
    async def kapot(messages, info):
        raise ModelHTTPError(status_code=500, model_name="nep", body="kapot")
        yield ""

    app.state.chatmodel = FunctionModel(stream_function=kapot)
    kb = (await client.post("/api/v1/kennisbanken", json={"naam": "HR"})).json()
    gesprek = (await client.post(f"/api/v1/kennisbanken/{kb['id']}/gesprekken", json={})).json()
    r = await client.post(f"/api/v1/gesprekken/{gesprek['id']}/berichten", json={"inhoud": "Hoi"})

    event, data = _sse_events(r.text)[-1]
    assert event == "fout"
    assert data["detail"].startswith("Het taalmodel gaf een fout")


async def test_onleesbaar_document_krijgt_status_fout(client, fake_ollama):
    kb = (await client.post("/api/v1/kennisbanken", json={"naam": "HR"})).json()
    url = f"/api/v1/kennisbanken/{kb['id']}/documenten"
    await client.post(url, files=[("bestanden", ("kapot.pdf", b"geen pdf", "application/pdf"))])

    await _verwerk_wachtrij(fake_ollama)
    doc = (await client.get(url)).json()[0]
    assert doc["status"] == "fout"
    assert doc["foutmelding"]


async def test_document_dat_backend_laat_crashen_wordt_fout(client, fake_ollama):
    kb = (await client.post("/api/v1/kennisbanken", json={"naam": "HR"})).json()
    url = f"/api/v1/kennisbanken/{kb['id']}/documenten"
    await client.post(url, files=[("bestanden", ("thuiswerken.md", DOC, "text/markdown"))])

    # Oppakken zonder af te ronden en dan herstarten: zo ziet een OOM-kill eruit.
    for _ in range(MAX_POGINGEN - 1):
        assert await claim_next(SessionLocal)
        await requeue_stuck(SessionLocal)
        assert (await client.get(url)).json()[0]["status"] == "wachtrij"

    assert await claim_next(SessionLocal)
    await requeue_stuck(SessionLocal)
    doc = (await client.get(url)).json()[0]
    assert doc["status"] == "fout"
    assert "afgebroken" in doc["foutmelding"]
    assert await claim_next(SessionLocal) is None


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
