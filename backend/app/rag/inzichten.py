"""Inzichten: het hele document lezen in plaats van zoeken.

Zoeken (retrieval) geeft het taalmodel maar een handvol fragmenten. Een vraag als 'welke
inzichten haal je hieruit?' heeft daar niets aan, en een samenvatting laat juist de details
weg waar het om gaat. Daarom lezen we elk document één keer helemaal, na het verwerken:

1. Lezen: het document in secties van een paar duizend tokens; per sectie vraagt het model
   om opvallende bevindingen, elk met de fragmenten waar ze op steunen.
2. Samenvoegen: dubbele bevindingen samenvoegen, onbelangrijke weglaten, ordenen op belang.

Na elke sectie geeft maak_inzichten de tussenstand door; wie die bewaart, kan na een herstart
verder waar hij was. Bij veel bevindingen gaat het samenvoegen in rondes, zodat één aanroep
niet groter wordt dan het taalmodel aankan.

Elk inzicht houdt de ids van zijn fragmenten, zodat het in de chat met bronnen te tonen is.
Een bevinding zonder geldig fragment vervalt: wat niet te herleiden is, bewaren we niet.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.rag.chunking import BenaderdeTokenizer

Soort = Literal["cijfer", "risico", "besluit", "afwijking", "tegenstrijdigheid", "overig"]

BEVINDINGPROMPT = """Je leest één sectie van een document en haalt er de inzichten uit die een \
beleidsmedewerker niet mag missen. Denk aan:
- cijfer: opvallende bedragen, percentages, trends of verschuivingen;
- risico: risico's, onzekerheden, voorbehouden en kanttekeningen (ook in voetnoten en bijlagen);
- besluit: besluiten, afspraken, toezeggingen en deadlines;
- afwijking: afwijkingen van eerdere plannen, ramingen of normen;
- tegenstrijdigheid: dingen die elkaar in de tekst tegenspreken;
- overig: andere dingen die echt opvallen.

Regels:
- Gebruik alleen wat in deze sectie staat. Verzin niets en trek geen conclusies die er niet staan.
- Schrijf elk inzicht in één tot drie zinnen, concreet, met de cijfers en namen uit de tekst.
- Geef bij elk inzicht de nummers van de fragmenten waar het op steunt.
- belang: 3 = moet de lezer weten, 2 = nuttig, 1 = detail.
- Liever een paar sterke inzichten dan veel zwakke. Staat er niets opvallends in de sectie \
(bijvoorbeeld alleen een inhoudsopgave of colofon), geef dan een lege lijst.
- Schrijf in de taal van het document.
"""

SAMENVOEGPROMPT = """Je krijgt genummerde bevindingen die per sectie uit één document zijn \
gehaald. Maak er de definitieve lijst inzichten van:
- Voeg bevindingen samen die over hetzelfde gaan en noem bij het inzicht alle nummers.
- Laat triviale of herhaalde bevindingen weg.
- Zet het belangrijkste bovenaan. Geef niet meer inzichten dan het maximum onder de lijst.
- Geef elk inzicht een kort thema van twee tot vier woorden.
- Houd de concrete cijfers en namen. Voeg niets toe dat niet in de bevindingen staat.
- Schrijf in de taal van de bevindingen.
"""


class Bevinding(BaseModel):
    thema: str = Field(description="Kort thema, twee tot vier woorden")
    tekst: str = Field(description="Het inzicht in één tot drie zinnen")
    soort: Soort
    belang: int = Field(description="3 = moet de lezer weten, 2 = nuttig, 1 = detail")
    fragmenten: list[int] = Field(description="Nummers van de fragmenten waar dit op steunt")


class Bevindingen(BaseModel):
    bevindingen: list[Bevinding]


class SamengevoegdInzicht(BaseModel):
    thema: str = Field(description="Kort thema, twee tot vier woorden")
    tekst: str = Field(description="Het inzicht in één tot drie zinnen")
    soort: Soort
    belang: int = Field(description="3 = moet de lezer weten, 2 = nuttig, 1 = detail")
    bevindingen: list[int] = Field(description="Nummers van de bevindingen die hierin opgaan")


class SamengevoegdeInzichten(BaseModel):
    inzichten: list[SamengevoegdInzicht]


bevinding_agent = Agent(name="bevindingen", instructions=BEVINDINGPROMPT, output_type=Bevindingen)
samenvoeg_agent = Agent(
    name="samenvoegen", instructions=SAMENVOEGPROMPT, output_type=SamengevoegdeInzichten
)


@dataclass
class Fragment:
    id: uuid.UUID
    tekst: str
    kopjes: list[str]
    pagina: int | None


@dataclass
class NieuwInzicht:
    thema: str
    tekst: str
    soort: str
    belang: int
    chunk_ids: list[uuid.UUID]


_tokenizer = BenaderdeTokenizer()


def secties(fragmenten: list[Fragment], max_tokens: int) -> list[list[Fragment]]:
    """Fragmenten op volgorde in secties van hooguit max_tokens. Een nieuw hoofdstuk begint
    liefst een nieuwe sectie, zodat een sectie over één onderwerp gaat."""
    uit: list[list[Fragment]] = []
    huidig: list[Fragment] = []
    tokens = 0
    for f in fragmenten:
        n = _tokenizer.count_tokens(f.tekst)
        hoofdstuk_wissel = bool(
            huidig and f.kopjes[:1] != huidig[-1].kopjes[:1] and tokens >= max_tokens // 2
        )
        if huidig and (tokens + n > max_tokens or hoofdstuk_wissel):
            uit.append(huidig)
            huidig, tokens = [], 0
        huidig.append(f)
        tokens += n
    if huidig:
        uit.append(huidig)
    return uit


def _sectietekst(bestandsnaam: str, sectie: list[Fragment]) -> str:
    delen = []
    for i, f in enumerate(sectie, start=1):
        kop = f"[{i}]"
        if f.pagina:
            kop += f" pagina {f.pagina}"
        if f.kopjes:
            kop += f" — {' > '.join(f.kopjes)}"
        delen.append(f"{kop}\n{f.tekst}")
    return f"Document: {bestandsnaam}\n\n" + "\n\n".join(delen)


def _belang(waarde: int) -> int:
    return min(3, max(1, waarde))


async def _lees_sectie(
    model: Model, bestandsnaam: str, sectie: list[Fragment], slot: asyncio.Semaphore
) -> list[NieuwInzicht]:
    async with slot:
        resultaat = await bevinding_agent.run(_sectietekst(bestandsnaam, sectie), model=model)
    uit = []
    for b in resultaat.output.bevindingen:
        ids = list(dict.fromkeys(sectie[n - 1].id for n in b.fragmenten if 1 <= n <= len(sectie)))
        if ids and b.tekst.strip():
            uit.append(
                NieuwInzicht(b.thema.strip(), b.tekst.strip(), b.soort, _belang(b.belang), ids)
            )
    return uit


async def _voeg_samen(
    model: Model, bevindingen: list[NieuwInzicht], maximum: int
) -> list[NieuwInzicht]:
    lijst = "\n\n".join(
        f"[{i}] ({b.soort}, belang {b.belang}, thema: {b.thema})\n{b.tekst}"
        for i, b in enumerate(bevindingen, start=1)
    )
    resultaat = await samenvoeg_agent.run(
        f"Bevindingen:\n\n{lijst}\n\nMaximum: {maximum} inzichten.", model=model
    )
    uit = []
    for s in resultaat.output.inzichten:
        bronnen = [bevindingen[n - 1] for n in s.bevindingen if 1 <= n <= len(bevindingen)]
        ids = list(dict.fromkeys(cid for b in bronnen for cid in b.chunk_ids))
        if ids and s.tekst.strip():
            uit.append(
                NieuwInzicht(s.thema.strip(), s.tekst.strip(), s.soort, _belang(s.belang), ids)
            )
    return uit[:maximum]


# Zoveel bevindingen gaan hooguit in één samenvoeg-aanroep (circa 6k tokens).
SAMENVOEG_PER_KEER = 60

Tussenstand = dict[int, list[NieuwInzicht]]


def naar_json(inzichten: list[NieuwInzicht]) -> list[dict]:
    return [{**asdict(i), "chunk_ids": [str(c) for c in i.chunk_ids]} for i in inzichten]


def uit_json(data: list[dict]) -> list[NieuwInzicht]:
    return [
        NieuwInzicht(**{**d, "chunk_ids": [uuid.UUID(c) for c in d["chunk_ids"]]}) for d in data
    ]


async def _voeg_samen_in_rondes(
    model: Model, bevindingen: list[NieuwInzicht], maximum: int
) -> list[NieuwInzicht]:
    while len(bevindingen) > SAMENVOEG_PER_KEER:
        groepen = [
            bevindingen[i : i + SAMENVOEG_PER_KEER]
            for i in range(0, len(bevindingen), SAMENVOEG_PER_KEER)
        ]
        rondes = await asyncio.gather(*(_voeg_samen(model, g, maximum) for g in groepen))
        nieuw = [b for r in rondes for b in r]
        if len(nieuw) >= len(bevindingen):  # het model voegde niets samen; niet eindeloos door
            break
        bevindingen = nieuw
    return await _voeg_samen(model, bevindingen, maximum)


async def maak_inzichten(
    model: Model,
    bestandsnaam: str,
    fragmenten: list[Fragment],
    sectie_tokens: int,
    maximum: int,
    gelijktijdig: int = 4,
    al_gelezen: Tussenstand | None = None,
    voortgang: Callable[[int, Tussenstand], Awaitable[None]] | None = None,
) -> list[NieuwInzicht]:
    """Leest alle fragmenten van een document (op volgorde) en geeft de inzichten, belangrijkste
    eerst. Mislukt één sectie, dan mislukt het geheel: half gelezen is wat we niet willen.

    al_gelezen: secties (op index) die eerder al gelezen zijn; die worden overgeslagen.
    voortgang(totaal, gelezen) wordt aan het begin en na elke sectie aangeroepen."""
    alle = secties(fragmenten, sectie_tokens)
    gelezen: Tussenstand = {i: b for i, b in (al_gelezen or {}).items() if i < len(alle)}
    slot = asyncio.Semaphore(gelijktijdig)
    # Eén tegelijk melden, zodat een latere tussenstand nooit door een eerdere wordt overschreven.
    meld = asyncio.Lock()

    async def lees(i: int) -> None:
        bevindingen = await _lees_sectie(model, bestandsnaam, alle[i], slot)
        async with meld:
            gelezen[i] = bevindingen
            if voortgang:
                await voortgang(len(alle), dict(gelezen))

    if voortgang:
        await voortgang(len(alle), dict(gelezen))
    # Een TaskGroup breekt de andere secties af als er een mislukt; gather liet ze doorlopen.
    try:
        async with asyncio.TaskGroup() as tg:
            for i in range(len(alle)):
                if i not in gelezen:
                    tg.create_task(lees(i))
    except ExceptionGroup as eg:
        raise eg.exceptions[0] from None

    bevindingen = [b for i in sorted(gelezen) for b in gelezen[i]]
    if not bevindingen:
        return []
    # Eén sectie met weinig bevindingen hoeft niet samengevoegd te worden.
    if len(alle) == 1 and len(bevindingen) <= maximum:
        return sorted(bevindingen, key=lambda b: -b.belang)
    return await _voeg_samen_in_rondes(model, bevindingen, maximum)
