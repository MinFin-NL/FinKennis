# Verantwoording inzet van generatieve AI in de PoC FinKennis

**Verantwoording in het kader van het Overheidsbreed Standpunt Generatieve AI, getoetst aan het
stappenplan uit de bijbehorende handreiking**

Dit document verantwoordt het gebruik van generatieve AI in deze Proof of Concept (PoC). Voor
een beknopte samenvatting, zie [`DISCLAIMER.md`](../DISCLAIMER.md).

## Beschrijving van de PoC en de rol van AI

FinKennis is een webapplicatie waarin overheidsmedewerkers kennisbanken maken: een
verzameling documenten waarover ze vragen stellen aan een AI-assistent. Zie de
[`README.md`](../README.md) voor de opzet en werking.

Generatieve AI speelt hier op **twee** manieren een rol. Dit document behandelt ze apart:

1. **AI bij het bouwen.** De code is grotendeels gegenereerd met de AI-assistant Claude Code
   (Anthropic). AI is ingezet voor codegeneratie, refactoring, testen en review.
2. **AI in de applicatie.** FinKennis gebruikt zelf twee taalmodellen. Een embeddingmodel maakt
   geüploade documenten doorzoekbaar. Een chatmodel beantwoordt vragen op basis van de
   gevonden fragmenten (retrieval-augmented generation). Beide modellen draaien lokaal via
   Ollama. Er gaan geen documenten of vragen naar een externe AI-dienst.

**Verantwoordelijkheid voor commits.** Ga ervan uit dat elke commit in deze repository met
behulp van Claude Code tot stand is gekomen, ook als dat niet apart in de commit staat. De
persoon die de commit maakt, blijft verantwoordelijk voor de inhoud: die heeft de wijziging
beoordeeld en goedgekeurd voordat die in de repository is opgenomen. De mens blijft
eindverantwoordelijk; de AI is een hulpmiddel.

**Menselijke tussenkomst in de applicatie.** Een AI-antwoord is altijd een hulpmiddel om
informatie te vinden, geen besluit. Bij elk antwoord ziet de gebruiker welke bronnen het
antwoord noemt, met bestandsnaam, pagina, kopje en het fragment zelf. Zo kan de gebruiker
het antwoord in het brondocument controleren. Onder het invoerveld staat steeds dat
antwoorden fouten kunnen bevatten.

**Gegevens.** Gebruikers uploaden eigen documenten in een kennisbank. Die kunnen
persoonsgegevens of vertrouwelijke informatie bevatten; de app kan dat niet uitsluiten.

**Scope-grens.** Deze verantwoording betreft uitsluitend de PoC en het testen ervan. Gebruik
in productie valt **buiten de huidige scope** en vereist aanvullende toetsing, waaronder een
beoordeling tegen de BIO (Baseline Informatiebeveiliging Overheid) en een DPIA (Data
Protection Impact Assessment).

## Verantwoording per stappenplan

Hieronder volgen we het globale stappenplan uit hoofdstuk 4 van de
[Overheidsbrede handreiking verantwoorde inzet van generatieve AI](https://open.overheid.nl/documenten/9c273b71-cebb-4e11-b06f-fa20f7b4b90e/file).

### 1) Doel en toepassingsgebied

*Doel (AI-aspect):*

- onderzoeken of we verantwoord met behulp van generatieve AI software kunnen bouwen die in
  lijn is met de standaarden en kaders van de Nederlandse overheid (onder andere het NLDD
  Designsysteem, WCAG 2.1 AA en de NL GOV API Design Rules), mede met behulp van de
  [overheidsskills](https://github.com/developer-overheid-nl/skills-marketplace);
- onderzoeken of een lokaal draaiend taalmodel medewerkers helpt om snel en controleerbaar
  informatie te vinden in grote sets documenten, zoals de stukken van Prinsjesdag.

*Toepassingsgebied:* de ontwikkeling van deze PoC en het testen ervan. Niet in scope: gebruik
in productie.

### 2) Zorg voor de juiste mensen en vaardigheden

De betrokken ontwikkelaars bouwen kennis op door iets te bouwen. Om de juiste expertise te
betrekken, streven we ernaar zo veel mogelijk betrokken partijen, waaronder privacy-,
security- en AI-experts en de beoogde gebruikers, te laten meekijken met de PoC.

### 3) Creëer een (generatieve) AI-governance structuur

Het werk gebeurt in opdracht van het Innovatieteam van het Ministerie van Financiën. Als
beleidsmatige leidraad gelden het
[Overheidsbreed standpunt voor de inzet van generatieve AI](https://open.overheid.nl/documenten/bc03ce31-0cf1-4946-9c94-e934a62ebe73/file)
en de bijbehorende
[handreiking](https://open.overheid.nl/documenten/9c273b71-cebb-4e11-b06f-fa20f7b4b90e/file).

Concrete governance-maatregelen:

- Elke commit geldt als met AI gegenereerd; de persoon die de commit maakt, is
  verantwoordelijk voor de inhoud (zie hierboven).
- Commits en pushes gebeuren alleen op uitdrukkelijk verzoek van de ontwikkelaar, nooit
  automatisch door de AI-assistant.
- In de applicatie noemt elk AI-antwoord zijn bronnen; de gebruiker beoordeelt het antwoord.
- In de applicatie staat bovenaan een oranje statusbalk dat dit een bètaversie is, met een
  contactadres voor vragen en feedback (innovatiemanagementfinancien@minfin.nl).
- Voor transparantie is de code gepubliceerd onder een open licentie
  ([EUPL-1.2](../LICENSE)); reageren kan via GitHub-issues.

### 4) Risicoanalyse

Deze applicatie gebruikt AI niet alleen als bouwgereedschap, maar bevat zelf een generatief
AI-component. Daarom gelden naast de risico's van AI-ondersteund ontwikkelen ook de risico's
van een AI-systeem dat overheidsmedewerkers ondersteunt.

#### a. Voldoen aan de EU AI-verordening

*Bij het bouwen:* Claude Code is gereedschap; de verplichtingen vallen primair op de
aanbieder (Anthropic). Anthropic heeft de
[General Purpose AI Code of Practice](https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai)
van de EU ondertekend.

*In de applicatie:* FinKennis helpt informatie te vinden in documenten en neemt geen
besluiten over burgers of bedrijven. De risicoclassificatie volgens de AI-verordening is
waarschijnlijk beperkt. Die moet nog worden vastgesteld met de
[beslishulp AI-verordening](https://github.com/MinBZK/ai-verordening-beslishulp). Omdat de
gebruiker met door AI gegenereerde tekst werkt, maakt de app duidelijk dat antwoorden van een
taalmodel komen en op welke bronnen ze steunen (transparantie, artikel 50).

#### b. AVG en DPIA

Documenten die gebruikers uploaden, kunnen persoonsgegevens bevatten. Omdat de taalmodellen
lokaal via Ollama draaien, verlaten documenten en vragen de eigen omgeving niet. Voor deze PoC
is nog geen DPIA uitgevoerd. Organisaties die deze code in productie willen nemen, dienen zelf
te beoordelen welke AVG-verplichtingen gelden, waaronder een DPIA.

#### c. BIO en beveiligingseisen

De PoC kent basismaatregelen:

- inloggen via Keycloak (OpenID Connect, Authorization Code met PKCE);
- de backend controleert elk access token (handtekening, uitgever, audience en geldigheid);
- elke kennisbank heeft één eigenaar, en een kennisbank van een ander geeft een 404;
- beperkingen op bestandstype en bestandsgrootte bij uploaden;
- antwoorden van het taalmodel worden als tekst getoond, nooit als HTML.

Geüploade documenten staan onversleuteld op schijf en in de database. Gebruik in productie
vereist een volledige toetsing aan de geldende beveiligingseisen.

#### d. Datadeling met de AI-aanbieder

*Bij het bouwen:* het risico wordt beperkt doordat geen vertrouwelijke gegevens of
persoonsgegevens aan de AI-assistant worden gegeven. De voorbeelddocumenten in
`docs/example/` zijn openbare overheidspublicaties. Daarnaast is de opt-out voor
modeltraining aangezet.

*In de applicatie:* de taalmodellen draaien lokaal en er wordt niets gedeeld met een
AI-aanbieder.

#### e. Risico op "schijnzekerheid"

Een antwoord met een bronverwijzing lijkt betrouwbaar, maar het taalmodel kan een bron
verkeerd samenvatten of een verkeerd getal overnemen. Het grootste inhoudelijke risico is dat
gebruikers antwoorden overnemen zonder ze in de bron te controleren. De officiële
brondocumenten zijn altijd leidend.

#### f. Kwaliteitsrisico: onjuiste of onveilige gegenereerde code en antwoorden

*Code:* de persoon die commit, beoordeelt de wijziging. Daarnaast zijn er geautomatiseerde
tests (pytest, tegen een echte database), typecontrole bij elke build (`vue-tsc`), linting
(`ruff`) en een CI-workflow die dit bij elke wijziging draait.

*Antwoorden in de app:*

- de systeemprompt draagt het model op alleen uit de bronnen te antwoorden, elke bewering
  met een bronnummer te onderbouwen en te zeggen wanneer het antwoord niet in de documenten
  staat;
- de app toont alleen de bronnen waar het antwoord echt naar verwijst;
- zoeken gebeurt zowel op betekenis als op trefwoorden, zodat exacte termen en getallen beter
  gevonden worden.

Er is nog geen evaluatieset waarmee prompts en modellen systematisch worden beoordeeld. Dat
is een aandachtspunt voor een vervolg.

#### g. Auteursrecht op brondocumenten als input

De voorbeelddocumenten zijn openbare publicaties van de Rijksoverheid en worden niet in de
repository opgenomen (zie `.gitignore`). Documenten die gebruikers uploaden, zijn hun eigen
verantwoordelijkheid.

#### h. Uitlegbaarheid / gevaar op "black box"

De code, de prompts en de architectuur zijn openbaar en in voor mensen leesbare vorm
gepubliceerd (zie de [`README.md`](../README.md) en
[`backend/app/rag/`](../backend/app/rag)). In de app is per antwoord zichtbaar op welke
fragmenten uit de documenten het steunt.

#### i. AI-geletterdheid van betrokken medewerkers

Kennis over de inzet van AI-assistants wordt binnen het team gedeeld; deze verantwoording
wordt openbaar gepubliceerd. Gebruikers van FinKennis moeten weten dat antwoorden fouten
kunnen bevatten en gecontroleerd moeten worden. Daarom staat dat in de app zelf: in de
oranje statusbalk bovenaan, bij de lege chat en onder het invoerveld.

### 5) Generatieve AI inkopen of bouwen

#### a. Vendor lock-in

*Bij het bouwen:* op dit moment wordt uitsluitend Claude Code gebruikt. Dat is een expliciet
aandachtspunt voor een eventueel vervolg. De opgeleverde software zelf (Vue/TypeScript en
Python/FastAPI) heeft geen afhankelijkheid van die AI-assistant; een andere assistant kan in
een vervolg worden ingezet.

*In de applicatie:* de taalmodellen zijn open-weight-modellen via Ollama en zijn met één
instelling te wisselen. Het chatmodel wordt aangesproken via
[Pydantic AI](https://ai.pydantic.dev), dat veel aanbieders ondersteunt. Het model wordt op één
plek gekozen ([`backend/app/llm/ollama.py`](../backend/app/llm/ollama.py)), zodat een andere
aanbieder daar kan worden aangesloten.

#### b. Keuze voor de AI-assistant en het taalmodel

Voor het bouwen is gekozen voor Claude Code (Anthropic), een aanbieder die de EU General
Purpose AI Code of Practice heeft ondertekend. Voor de applicatie zijn lokale open modellen de
standaard (`qwen3:8b` voor de antwoorden, `nomic-embed-text` voor het zoeken), zodat gegevens
de eigen omgeving niet hoeven te verlaten.
