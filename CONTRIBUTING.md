# Bijdragen aan FinKennis

Fijn dat je wilt bijdragen. Dit document beschrijft hoe je dat doet.

## Een probleem of idee melden

Open een [issue](https://github.com/MinFin-NL/FinKennis/issues). Beschrijf:

- wat je deed en wat je verwachtte;
- wat er gebeurde, met de foutmelding als die er is;
- je omgeving: besturingssysteem, het Ollama-model en de versie van FinKennis.

Een **beveiligingsprobleem** meld je niet in een issue. Zie [SECURITY.md](SECURITY.md).

## Code bijdragen

1. Fork de repository en maak een branch vanaf `main`, bijvoorbeeld `fix/upload-grote-pdf`.
2. Zet je omgeving op zoals beschreven in de [README](README.md#lokaal-draaien).
3. Maak je wijziging. Voeg tests toe of pas ze aan in `backend/tests/`.
4. Controleer dat alles slaagt:

   ```bash
   make lint
   make test
   ```

5. Open een pull request. Beschrijf wat je wijzigt en waarom, en verwijs naar het issue.

### Afspraken

- **Taal.** De domeinbegrippen zijn Nederlands (kennisbank, document, gesprek, bericht), in
  de code, in de API en in de interface. Technische termen blijven Engels.
- **Backend.** Python 3.11+, opgemaakt en gecontroleerd met `ruff`. Wijzigingen aan het
  datamodel gaan via een Alembic-migratie (`uv run alembic revision --autogenerate`). Lees de
  gegenereerde migratie altijd na.
- **API.** Volg de [NL GOV API Design Rules](https://gitdocumentatie.logius.nl/publicatie/api/adr/):
  fouten als `problem+json`, en geen breaking changes binnen `/api/v1`.
- **Frontend.** Gebruik componenten van het [NLDD Designsysteem](https://nederlandsedigitaledienst.github.io/design-system/)
  en stuur ze via hun attributen. Schrijf geen CSS die in de shadow DOM grijpt. Mist er iets
  in een component, meld het dan bij het designsysteem.
- **Toegankelijkheid.** De interface moet voldoen aan WCAG 2.1 AA. Test nieuwe schermen met het
  toetsenbord en op 200% zoom.
- **Privacy.** Zet nooit echte documenten, persoonsgegevens of geheimen in tests, issues of
  commits.
- **Commits.** Schrijf korte, beschrijvende commitberichten in de gebiedende wijs, zoals
  "Voeg OCR-optie toe voor gescande PDF's".

## Gedragscode

Iedereen die bijdraagt houdt zich aan de [gedragscode](CODE_OF_CONDUCT.md).

## Licentie

Door bij te dragen ga je ermee akkoord dat je bijdrage valt onder de
[EUPL-1.2](LICENSE), dezelfde licentie als de rest van het project.
