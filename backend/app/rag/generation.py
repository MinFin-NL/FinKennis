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


def bouw_berichten(
    vraag: str, bronnen: list[Bron], geschiedenis: list[tuple[str, str]]
) -> list[dict]:
    """geschiedenis: (rol, inhoud) van eerdere berichten, oudste eerst."""
    berichten = [{"role": "system", "content": SYSTEEMPROMPT}]
    berichten += [{"role": rol, "content": inhoud} for rol, inhoud in geschiedenis]
    berichten.append(
        {
            "role": "user",
            "content": f"Bronnen:\n\n{bronnen_context(bronnen)}\n\n---\n\nVraag: {vraag}",
        }
    )
    return berichten
