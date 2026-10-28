# Beveiliging

## Een kwetsbaarheid melden

Heb je een kwetsbaarheid gevonden in FinKennis? Meld die dan **niet** in een openbaar issue
of pull request.

FinKennis valt onder de Rijksoverheid. Meld een kwetsbaarheid via de
[Coordinated Vulnerability Disclosure van het NCSC](https://www.ncsc.nl/contact/kwetsbaarheid-melden).

Vermeld in je melding:

- welk onderdeel het betreft (backend, frontend, de afhankelijkheden, de configuratie);
- hoe de kwetsbaarheid te reproduceren is;
- wat de mogelijke impact is.

We bevestigen je melding zo snel mogelijk en houden je op de hoogte van de afhandeling.
Maak de kwetsbaarheid niet openbaar voordat die is verholpen.

## Ondersteunde versies

Alleen de laatste versie op `main` krijgt beveiligingsupdates.

## Aandachtspunten bij gebruik

- Draai FinKennis buiten je eigen machine alleen met `AUTH_MODE=oidc`. Met `AUTH_MODE=none`
  delen alle gebruikers dezelfde kennisbanken.
- De Keycloak-realm in `keycloak/` en de wachtwoorden in `docker-compose.yml` zijn alleen
  voor ontwikkeling.
- Geüploade documenten staan onversleuteld in `UPLOAD_DIR` en in de database. Bescherm die
  opslag zoals je de documenten zelf beschermt.
