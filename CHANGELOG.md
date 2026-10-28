# Changelog

Alle noemenswaardige wijzigingen aan dit project staan in dit bestand.

Het formaat is gebaseerd op [Keep a Changelog](https://keepachangelog.com/nl/1.1.0/) en dit
project volgt [Semantic Versioning](https://semver.org/lang/nl/).

## [Unreleased]

### Toegevoegd

- Kennisbanken aanmaken, bewerken en verwijderen.
- Documenten uploaden (PDF, DOCX, PPTX, XLSX, ODT, HTML, Markdown, tekst, CSV). Ze worden op
  de achtergrond ingelezen met docling, structuurbewust gechunkt en ge-embed via Ollama.
- Dubbele uploads worden herkend aan hun sha256.
- Hybride zoeken met pgvector en Nederlandse full-text, samengevoegd met Reciprocal Rank Fusion.
- Chat met gestreamde antwoorden en bronverwijzingen (bestand, pagina, kopje); eerdere
  gesprekken blijven bewaard.
- Vervolgvragen in een gesprek: een vraag als "en voor deeltijders?" wordt met het eerdere
  gesprek herschreven tot een zelfstandige zoekvraag, zodat de juiste bronnen gevonden worden.

### Gewijzigd

- Het chatmodel wordt aangesproken via Pydantic AI in plaats van een eigen Ollama-client.
  Embeddings en de health-check gaan nog rechtstreeks naar de Ollama-API.
- Interface met het NLDD Designsysteem, ook bruikbaar op mobiel.
- Optionele login via OIDC (Keycloak). Elke gebruiker ziet alleen zijn eigen kennisbanken.
- REST-API volgens de NL GOV API Design Rules, met OpenAPI-specificatie.
- DISCLAIMER.md, een verantwoording van het AI-gebruik (`docs/ai-verantwoording.md`) en een
  vaste melding in de chat dat antwoorden door AI worden gemaakt.
- Oranje statusbalk bovenaan de app, gelijk aan de invulhulp: bètaversie, met contactadres van
  het Innovatieteam MinFin.
