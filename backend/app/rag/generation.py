import re
import uuid
from dataclasses import dataclass, field

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

# Eén regel waarmee het model zijn eigen redenering begint. De frontend toont alles daarna
# in een apart kader met 'Niet uit de documenten'.
MEEDENKEN = "Meedenken:"

CHATPROMPT = """Je bent de assistent van FinKennis. Je praat met de gebruiker over de documenten \
in de kennisbank. Je krijgt twee soorten genummerde bronnen:
- Fragmenten: stukken tekst uit de documenten die bij de vraag of het gesprek passen, per \
document bij elkaar. Ze komen uit de documenten die het best bij de vraag passen, ook als iets \
daar niet als inzicht is bewaard.
- Inzichten: bevindingen die vooraf uit de documenten zijn gehaald door elk document helemaal te \
lezen, per document bij elkaar, met het stuk tekst waar ze op steunen.

Feiten uit de documenten:
- Alles wat je over de inhoud van de documenten zegt, komt uit de bronnen en krijgt het nummer \
van de bron, zo: [1] of [2][3]. Verzin niets en laat een bron niets zeggen wat er niet staat.
- Eerdere antwoorden in dit gesprek zijn geen bron. Herhaal iets uit het gesprek alleen als de \
bronnen van nu het ook zeggen.
- Staat het antwoord niet in de bronnen, zeg dat dan eerlijk.

Kies de vorm die bij de vraag past:
- Vraagt de gebruiker een feit (een bedrag, datum, regel), geef dan een kort antwoord met bron.
- Vraagt de gebruiker wat er opvalt, om een overzicht of om inzichten, gebruik dan vooral de \
inzichten. Groepeer per thema met het thema als **vetgedrukte** regel boven een opsomming, het \
belangrijkste eerst, met de concrete cijfers en namen.
- Kijk bij zo'n vraag ook naar verbanden tussen documenten: wat terugkomt in twee of meer \
documenten, wat verandert tussen documenten (let op jaartallen) en waar documenten elkaar \
tegenspreken. Zet die bovenaan onder **Verbanden tussen documenten**, noem de documenten en \
verwijs naar bronnen uit elk document. Liever geen verband dan een gezocht verband.

Zelf meedenken:
- Vraagt de gebruiker waarom iets zo is, wat het betekent, wat de gevolgen kunnen zijn of wat \
je zou doen, dan mag je meedenken met je eigen redenering en algemene kennis. Zet die altijd \
aan het eind van je antwoord, na een regel die alleen bestaat uit '{MEEDENKEN}'. Alles na die \
regel wordt getoond als 'niet uit de documenten'.
- Geef eerst wat de documenten er zelf over zeggen (met bronnen); de redenering komt daarna. \
Je mag in de redenering naar bronnen verwijzen waar je op voortbouwt.
- Bij een gewone feitenvraag denk je niet mee: dan geen '{MEEDENKEN}'-deel.
- Buiten dat deel gebruik je nooit eigen kennis.

Antwoord in de taal van de vraag, standaard in het Nederlands. Schrijf helder en beknopt, \
in B1-taal waar dat kan.
""".replace("{MEEDENKEN}", MEEDENKEN)


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


antwoord_agent = Agent(name="antwoord", instructions=CHATPROMPT)
herschrijf_agent = Agent(name="herschrijf", instructions=HERSCHRIJFPROMPT)


async def herschrijf(model: Model, vraag: str, geschiedenis: list[tuple[str, str]]) -> str:
    """Maakt van een vervolgvraag een zoekvraag die zonder het gesprek te begrijpen is."""
    resultaat = await herschrijf_agent.run(
        f"{_gesprekstekst(geschiedenis)}\nVervolgvraag: {vraag}\nZoekvraag:",
        model=model,
    )
    return resultaat.output.strip() or vraag


@dataclass
class Context:
    """Wat het model bij een vraag te zien krijgt.

    fragmenten: eerst de bronnen waar eerdere antwoorden naar verwezen, dan wat bij de vraag
    gevonden is. inzichten: per document bij elkaar. eerdere_inzichten: per chunk-id het
    inzicht dat er in een eerder antwoord bij hoorde."""

    fragmenten: list[Bron]
    inzichten: list[GevondenInzicht]
    eerdere_inzichten: dict[uuid.UUID, str] = field(default_factory=dict)

    def bronnen(self) -> list[Bron]:
        """In de volgorde van de nummers in de prompt: eerst de fragmenten, dan de inzichten."""
        return [*self.fragmenten, *(g.bron for g in self.inzichten)]

    def bronnen_json(self) -> list[dict]:
        uit = [b.as_dict(i) for i, b in enumerate(self.bronnen(), start=1)]
        for d, b in zip(uit, self.fragmenten, strict=False):
            if inzicht := self.eerdere_inzichten.get(b.chunk_id):
                d["inzicht"] = inzicht
        # Het inzicht bewaren, zodat een vervolgvraag weet waar het antwoord over ging.
        for d, g in zip(uit[len(self.fragmenten) :], self.inzichten, strict=True):
            d["inzicht"] = g.tekst
        return uit


def _kop(b: Bron) -> str:
    kop = b.bestandsnaam
    if b.pagina:
        kop += f", pagina {b.pagina}"
    return kop


def vraag_met_context(vraag: str, ctx: Context) -> str:
    nummer = 0
    delen = []
    if ctx.fragmenten:
        regels = []
        huidig = None
        for b in ctx.fragmenten:
            nummer += 1
            if b.document_id != huidig:
                huidig = b.document_id
                regels.append(f"## Document: {b.bestandsnaam}")
            kop = f"[{nummer}] {_kop(b)}"
            if b.kopjes:
                kop += f" — {' > '.join(b.kopjes)}"
            inzicht = ctx.eerdere_inzichten.get(b.chunk_id)
            tekst = f"Eerder inzicht hierover: {inzicht}\n{b.tekst}" if inzicht else b.tekst
            regels.append(f"{kop}\n{tekst}")
        delen.append("# Fragmenten\n\n" + "\n\n".join(regels))
    if ctx.inzichten:
        regels = []
        huidig = None
        for g in ctx.inzichten:
            nummer += 1
            if g.bron.document_id != huidig:
                huidig = g.bron.document_id
                regels.append(f"## Document: {g.bron.bestandsnaam}")
            regels.append(
                f"[{nummer}] {g.thema} ({g.soort}, belang {g.belang}) — {_kop(g.bron)}\n"
                f"Inzicht: {g.tekst}\nUit de tekst: {g.bron.tekst[:600]}"
            )
        delen.append("# Inzichten\n\n" + "\n\n".join(regels))
    if not delen:
        delen.append("Er zijn geen bronnen gevonden in de kennisbank.")
    return "\n\n---\n\n".join(delen) + f"\n\n---\n\nVraag: {vraag}"
