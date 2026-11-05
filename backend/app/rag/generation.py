import re

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import Model

from app.rag.retrieval import Bron, GevondenInzicht

SYSTEEMPROMPT = """Je bent de assistent van FinKennis. Je beantwoordt vragen uitsluitend op basis \
van de bronnen uit de kennisbank van de gebruiker.

Regels:
- Gebruik alleen informatie uit de bronnen hieronder. Verzin niets.
- Verwijs na elke bewering naar de bron(nen) met hun nummer, zo: [1] of [2][3].
- Staat het antwoord niet in de bronnen, zeg dan eerlijk dat je het niet in de documenten kunt \
vinden. Geef in dat geval geen antwoord uit eigen kennis.
- Vraagt de gebruiker om inzichten, een samenvatting of wat er opvalt in een of meer documenten, \
zeg dan dat je hier alleen losse feiten uit gevonden tekst geeft, en dat hij daarvoor onderaan \
het scherm 'Inzichten' kan kiezen. Geef wel wat de bronnen hierover zeggen.
- Antwoord in de taal van de vraag, standaard in het Nederlands. Schrijf helder en beknopt, \
in B1-taal waar dat kan.
"""

INZICHTPROMPT = """Je bent de assistent van FinKennis. Je krijgt inzichten die vooraf uit de \
documenten in de kennisbank zijn gehaald door elk document helemaal te lezen. Elk inzicht heeft \
een nummer, een thema en een stuk van de tekst waar het op steunt.

Regels:
- Kies de inzichten die het best bij de vraag passen. Is de vraag algemeen ('wat valt op?'), \
kies dan de belangrijkste.
- Groepeer ze per thema, het belangrijkste eerst. Zet elk thema als **vetgedrukte** regel \
boven een opsomming van de inzichten. Noem per inzicht de concrete cijfers en namen.
- Verwijs na elk inzicht naar zijn nummer, zo: [1] of [2][3].
- Gebruik alleen wat in de inzichten en de tekst eronder staat. Verzin niets.
- Passen de inzichten niet bij de vraag, zeg dat dan eerlijk en stel voor de vraag als gewone \
vraag te stellen.
- Antwoord in de taal van de vraag, standaard in het Nederlands. Schrijf helder en beknopt, \
in B1-taal waar dat kan.
"""


HERSCHRIJFPROMPT = """Je herschrijft een vervolgvraag tot een zoekvraag voor een zoekmachine die \
het gesprek niet kent. Zet het onderwerp uit het gesprek er dus letterlijk in: vervang woorden \
als 'dat', 'die', 'het' of 'hij' door waar ze naar verwijzen, en vul een vraag als \
'en voor deeltijders?' aan tot een volledige vraag. Staat de vraag al op zichzelf, of gaat hij \
over iets nieuws, geef hem dan ongewijzigd terug. Beantwoord de vraag niet. Geef alleen de \
herschreven vraag terug, in de taal van de vervolgvraag.

Voorbeeld:
Gebruiker: Hoeveel verlofdagen heb ik per jaar?
Assistent: Bij een fulltime dienstverband heb je 25 verlofdagen per jaar.
Vervolgvraag: En als ik 32 uur werk?
Zoekvraag: Hoeveel verlofdagen per jaar heb ik als ik 32 uur per week werk?
"""

# Bronnummers in eerdere antwoorden horen bij de bronnen van toen, niet bij die van nu.
_BRONVERWIJZING = re.compile(r"\[\d+\]")


def zonder_bronverwijzingen(tekst: str) -> str:
    return _BRONVERWIJZING.sub("", tekst)


def _gesprekstekst(geschiedenis: list[tuple[str, str]]) -> str:
    return "\n".join(
        f"{'Gebruiker' if rol == 'user' else 'Assistent'}: {zonder_bronverwijzingen(inhoud)}"
        for rol, inhoud in geschiedenis
    )


def als_berichten(geschiedenis: list[tuple[str, str]]) -> list[ModelMessage]:
    """geschiedenis: (rol, inhoud) van eerdere berichten, oudste eerst."""
    berichten: list[ModelMessage] = []
    for rol, inhoud in geschiedenis:
        tekst = zonder_bronverwijzingen(inhoud)
        if rol == "user":
            berichten.append(ModelRequest(parts=[UserPromptPart(tekst)]))
        else:
            berichten.append(ModelResponse(parts=[TextPart(tekst)]))
    return berichten


antwoord_agent = Agent(name="antwoord", instructions=SYSTEEMPROMPT)
inzicht_agent = Agent(name="inzichten", instructions=INZICHTPROMPT)
herschrijf_agent = Agent(name="herschrijf", instructions=HERSCHRIJFPROMPT)


async def herschrijf(model: Model, vraag: str, geschiedenis: list[tuple[str, str]]) -> str:
    """Maakt van een vervolgvraag een zoekvraag die zonder het gesprek te begrijpen is."""
    resultaat = await herschrijf_agent.run(
        f"{_gesprekstekst(geschiedenis)}\nVervolgvraag: {vraag}\nZoekvraag:",
        model=model,
    )
    return resultaat.output.strip() or vraag


def bronnen_context(bronnen: list[Bron]) -> str:
    if not bronnen:
        return "Er zijn geen relevante bronnen gevonden in de kennisbank."
    delen = []
    for i, b in enumerate(bronnen, start=1):
        kop = f"[{i}] {b.bestandsnaam}"
        if b.pagina:
            kop += f", pagina {b.pagina}"
        if b.kopjes:
            kop += f" — {' > '.join(b.kopjes)}"
        delen.append(f"{kop}\n{b.tekst}")
    return "\n\n---\n\n".join(delen)


def vraag_met_bronnen(vraag: str, bronnen: list[Bron]) -> str:
    return f"Bronnen:\n\n{bronnen_context(bronnen)}\n\n---\n\nVraag: {vraag}"


def vraag_met_inzichten(vraag: str, inzichten: list[GevondenInzicht]) -> str:
    delen = []
    for i, g in enumerate(inzichten, start=1):
        kop = f"[{i}] {g.thema} ({g.soort}, belang {g.belang}) — {g.bron.bestandsnaam}"
        if g.bron.pagina:
            kop += f", pagina {g.bron.pagina}"
        delen.append(f"{kop}\nInzicht: {g.tekst}\nUit de tekst: {g.bron.tekst[:600]}")
    lijst = "\n\n---\n\n".join(delen)
    return f"Inzichten:\n\n{lijst}\n\n---\n\nVraag: {vraag}"
