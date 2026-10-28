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

from app.rag.retrieval import Bron

SYSTEEMPROMPT = """Je bent de assistent van FinKennis. Je beantwoordt vragen uitsluitend op basis \
van de bronnen uit de kennisbank van de gebruiker.

Regels:
- Gebruik alleen informatie uit de bronnen hieronder. Verzin niets.
- Verwijs na elke bewering naar de bron(nen) met hun nummer, zo: [1] of [2][3].
- Staat het antwoord niet in de bronnen, zeg dan eerlijk dat je het niet in de documenten kunt \
vinden. Geef in dat geval geen antwoord uit eigen kennis.
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
