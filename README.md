# FinKennis

> ⚠️ **Proof of concept.** Dit is een vroege proof of concept van het Innovatieteam MinFin en
> niet klaar voor productie. We zoeken feedback en mensen om mee samen te werken aan de
> volgende stap: mail [innovatiemanagementfinancien@minfin.nl](mailto:innovatiemanagementfinancien@minfin.nl) of
> open een issue als je ideeën hebt. De meeste code is gegenereerd met Claude Code; zie
> [DISCLAIMER.md](DISCLAIMER.md) en de [verantwoording van het AI-gebruik](docs/ai-verantwoording.md).

FinKennis is een applicatie waarin je **kennisbanken** maakt: een verzameling documenten waar
je met een AI-assistent over kunt praten. Je uploadt documenten (PDF, Word, PowerPoint, Excel,
ODT, HTML, Markdown, tekst of CSV). FinKennis leest ze, deelt ze op in fragmenten en maakt ze
doorzoekbaar. Daarna stel je vragen en krijg je een antwoord met verwijzingen naar de bronnen:
bestand, pagina en kopje.

De interface is gebouwd met het [NLDD Designsysteem](https://nederlandsedigitaledienst.github.io/design-system/).
Lokaal draait het taalmodel via [Ollama](https://ollama.com) en gaan er geen documenten naar
een externe AI-dienst. In Azure gebruikt FinKennis dezelfde Azure OpenAI-modellen als de
invulhulp; zie [Uitrollen naar Azure](#uitrollen-naar-azure).

> **Let op:** antwoorden worden gemaakt door een taalmodel en kunnen fouten bevatten. De
> assistent is ingesteld om alleen uit de documenten te antwoorden en altijd zijn bronnen te
> noemen. Controleer belangrijke antwoorden in het brondocument.

## Hoe het werkt

```
frontend (Vue 3 + NLDD)  ──/api/v1──►  backend (FastAPI)
                                        ├─ inlezen: docling → structuurbewust chunken → embeddings (Ollama)
                                        ├─ zoeken: pgvector (semantisch) + full-text (Nederlands), samengevoegd met RRF
                                        ├─ antwoorden: Ollama-chatmodel via Pydantic AI, gestreamd als server-sent events
                                        └─ authenticatie: geen (lokaal) of OIDC (Keycloak)
PostgreSQL + pgvector: kennisbanken, documenten, fragmenten met vectoren, gesprekken
```

- **Inlezen.** Een upload wordt direct opgeslagen; een achtergrondworker pakt hem op
  (`FOR UPDATE SKIP LOCKED`, dus veilig met meerdere workers). [docling](https://github.com/docling-project/docling)
  leest de structuur van het document (kopjes, tabellen, pagina's). De HybridChunker houdt
  kopjes bij hun tekst en hakt tabellen niet doormidden. Fragmenten worden per 32 ge-embed met
  `nomic-embed-text`. Een bestand dat al in de kennisbank staat, wordt herkend aan zijn
  sha256 en overgeslagen.
- **Zoeken.** Elke vraag zoekt op twee manieren binnen de kennisbank: op betekenis (HNSW-index
  in pgvector) en op trefwoorden (Postgres full-text met Nederlandse stemming). De twee
  ranglijsten worden samengevoegd met Reciprocal Rank Fusion. Zo vind je zowel "hoeveel
  verlof bij verhuizing" als een exact artikelnummer.
- **Antwoorden.** De beste 6 fragmenten gaan met de vraag en de laatste berichten naar het
  chatmodel (standaard `qwen3:8b`). Het antwoord wordt token voor token gestreamd.

## Lokaal draaien

Je hebt nodig: Docker, [uv](https://docs.astral.sh/uv/), Node.js 20.19+ en
[Ollama](https://ollama.com).

```bash
# 1. Modellen ophalen
ollama pull qwen3:8b
ollama pull nomic-embed-text

# 2. Configuratie
cp .env.example .env

# 3. Afhankelijkheden, database en migraties
make install
make db
make migrate

# 4. Starten: backend op :8400, frontend op http://localhost:5190
make dev
```

De eerste keer dat je een PDF inleest, downloadt docling zijn layoutmodellen (een paar
honderd MB). Daarna werkt het offline.

### Configuratie

Alle instellingen staan in `.env` (zie [`.env.example`](.env.example)). De belangrijkste:

| Variabele | Standaard | Wat het doet |
| --- | --- | --- |
| `LLM_PROVIDER` | `ollama` | `ollama` lokaal, `azure_openai` in Azure (zie `AZURE_OPENAI_*` in `.env.example`). |
| `CHAT_MODEL` | `qwen3:8b` | Ollama-model voor de antwoorden. `mistral-small3.1:24b` is zwaarder maar beter. |
| `EMBED_MODEL` | `nomic-embed-text` | Model voor de embeddings. Wissel je dit, pas dan ook `EMBED_DIM` aan en maak een nieuwe migratie. |
| `MAX_UPLOAD_MB` | `50` | Maximale grootte per bestand. |
| `INGEST_CONCURRENCY` | `1` | Aantal documenten dat tegelijk wordt ingelezen. |
| `AUTH_MODE` | `none` | `none` voor lokaal gebruik, `oidc` voor Keycloak. |

De poorten zijn aan te passen: `make dev BACKEND_PORT=8000`, en `DB_PORT` en `KEYCLOAK_PORT`
voor Docker Compose.

## Inloggen met Keycloak

Met `AUTH_MODE=oidc` ziet wie niet is ingelogd eerst een landingspagina met de knop "Inloggen
met SSO". Elke gebruiker heeft zijn eigen kennisbanken en gesprekken. Een kennisbank van een
ander geeft een 404: de API verraadt niet dat hij bestaat.

Er zijn twee realm-rollen:

| Rol | Mag |
| --- | --- |
| `gebruiker` | Eigen kennisbanken maken, documenten uploaden en er vragen over stellen. |
| `beheerder` | Daarnaast gebruikersbeheer, via het accountmenu rechtsboven in de zijbalk. |

Gebruikersbeheer werkt zoals in de invulhulp: een beheerder maakt een gebruiker aan, die
krijgt een tijdelijk wachtwoord en kiest bij de eerste login een eigen wachtwoord. Een
beheerder kan ook wachtwoorden resetten, de beheerdersrol toekennen of afnemen, gebruikers
(de)activeren en verwijderen. Bij verwijderen gaan de kennisbanken van die gebruiker mee,
met alle documenten en gesprekken. Een beheerder kan zichzelf niet deactiveren, verwijderen
of de beheerdersrol afnemen. De backend praat daarvoor met de Keycloak Admin REST API via
het service account van de client `finkennis-admin` (rollen `manage-users`, `view-users` en
`view-realm`). Rollen zitten in het access token; een gewijzigde rol telt binnen vijf
minuten.

```bash
make auth   # start Keycloak op :8180 met realm 'finkennis'
            # testgebruikers: anna/anna (beheerder) en bram/bram (gebruiker)
```

Draaide Keycloak al met een oudere versie van de realm, dan slaat de import hem over. Maak
de container dan opnieuw aan: `docker compose --profile auth rm -sf keycloak && make auth`.

Zet dan in `.env`:

```bash
AUTH_MODE=oidc
OIDC_ISSUER=http://localhost:8180/realms/finkennis
OIDC_AUDIENCE=finkennis-api
OIDC_ADMIN_CLIENT_ID=finkennis-admin
OIDC_ADMIN_CLIENT_SECRET=dev-admin-secret-change-me
```

en in `frontend/.env`:

```bash
VITE_AUTH_MODE=oidc
VITE_OIDC_AUTHORITY=http://localhost:8180/realms/finkennis
VITE_OIDC_CLIENT_ID=finkennis-frontend
```

De frontend logt in met Authorization Code + PKCE. De backend controleert het access token
(handtekening via de JWKS van Keycloak, `iss`, `aud` en `exp`) en gebruikt `sub` als eigenaar.
De realm in [`keycloak/finkennis-realm.json`](keycloak/finkennis-realm.json) is alleen voor
ontwikkeling. Gebruik in productie een eigen realm, zonder testgebruikers.

## Uitrollen naar Azure

[`azure-pipelines.yml`](azure-pipelines.yml) rolt FinKennis uit naar de innovatie-omgeving
(`inno-d`), naast de invulhulp: dezelfde resource group (`rg-invulhulp-inno-d`), hetzelfde
Container Apps-environment en dezelfde container registry. De Azure-resources staan in
[`azure/main.bicep`](azure/main.bicep).

```
cae-invulhulp-inno-d
├── ca-finkennis-frontend-inno-d   nginx + SPA, publiek, zelfde IP-allowlist als de invulhulp
├── ca-finkennis-backend-inno-d    FastAPI, alleen intern bereikbaar; uploads op Azure Files
├── ca-finkennis-postgres-inno-d   pgvector, interne TCP-ingress op :5433
└── ca-keycloak-inno-d             gedeelde Keycloak (innovatieteam-infra), realm 'finkennis'
```

- **Taalmodel.** De backend draait met `LLM_PROVIDER=azure_openai` op dezelfde deployments
  als de invulhulp: `gpt-5.3-chat` voor de antwoorden en `text-embedding-3-large` voor de
  embeddings. Die laatste vraagt de backend op in 768 dimensies, zodat het databaseschema
  gelijk blijft aan lokaal.
- **Database.** Een Flexible Server mag niet van de CCoE-policy. Postgres draait daarom als
  container, net als de database van Keycloak, op een EmptyDir: na een herstart of
  platformonderhoud is de schijf leeg. Daarom dumpt een Container Apps-job
  ([`azure/pg-backup.sh`](azure/pg-backup.sh)) de database elke nacht (02:00 UTC) naar de share
  `finkennis-pgbackup`, en de pipeline doet dat ook vlak voor elke deploy. Start Postgres op
  een lege schijf, dan zet [`azure/pg-restore.sh`](azure/pg-restore.sh) eerst de nieuwste
  dump terug. Na een herstart ben je kwijt wat er sinds de laatste dump (die nacht of de
  laatste deploy) is gebeurd. De share bewaart de laatste drie dumps. Lukt het terugzetten niet, dan start
  Postgres niet. Dat is expres: anders zou hij leeg beginnen. Verwijder in dat geval de
  kapotte nieuwste dump, dan pakt Postgres de vorige.
  `FORCE_PG_REINIT=true` maakt een nieuwe replica, die de verse dump terugzet.
- **Inloggen.** De realm `finkennis` staat in de gedeelde Keycloak, in
  `innovatieteam-infra/keycloak/realms/finkennis-realm.json`. Draai die pipeline eerst. Er
  zitten geen testgebruikers in. Maak de eerste beheerder aan in de Keycloak-adminconsole
  (realm `finkennis`, rollen `gebruiker` en `beheerder`). Daarna gaat gebruikersbeheer via de
  app zelf.

Eenmalig in Azure DevOps (Pipelines > Library):

| Variable group | Variabele | |
| --- | --- | --- |
| `invulhulp-secrets` | `AZURE_SERVICE_CONNECTION`, `AZURE_OPENAI_*`, `ALLOWED_IP_1..4` | Bestaat al; gedeeld met de invulhulp. |
| `keycloak-secrets` | `FINKENNIS_ADMIN_CLIENT_SECRET` (secret) | Nieuw. Ook nodig in de Keycloak-pipeline. `openssl rand -hex 24`. |
| `keycloak-secrets` | `FINKENNIS_PUBLIC_URL` | Optioneel, alleen bij een eigen domein. |
| `finkennis-secrets` | `FINKENNIS_PG_PASSWORD` (secret) | Nieuwe groep. Alleen letters en cijfers: `openssl rand -hex 24`. |

Volgorde bij de eerste keer: de Keycloak-pipeline (met de nieuwe realm), dan deze pipeline.

## API

De API volgt de [NL GOV API Design Rules](https://gitdocumentatie.logius.nl/publicatie/api/adr/):
resources in het meervoud onder `/api/v1`, fouten als `application/problem+json`, en een
`API-Version`-header. De OpenAPI-specificatie staat op `/api/v1/openapi.json`. Een
interactieve weergave staat op `/api/v1/docs`.

| Methode | Pad | |
| --- | --- | --- |
| `GET` `POST` | `/kennisbanken` | Kennisbanken van de gebruiker |
| `GET` `PATCH` `DELETE` | `/kennisbanken/{id}` | |
| `GET` `POST` | `/kennisbanken/{id}/documenten` | Uploaden (multipart, `bestanden`), status volgen |
| `DELETE` | `/kennisbanken/{id}/documenten/{documentId}` | |
| `GET` `POST` | `/kennisbanken/{id}/gesprekken` | |
| `GET` `DELETE` | `/gesprekken/{id}` | Met alle berichten |
| `POST` | `/gesprekken/{id}/berichten` | Vraag stellen; antwoord als `text/event-stream` (`bronnen`, `token`, `klaar`, `fout`) |
| `GET` | `/mij` | De ingelogde gebruiker, met `beheerder` |
| `GET` `POST` | `/gebruikers` | Alleen beheerder. Aanmaken geeft een tijdelijk wachtwoord |
| `PATCH` `DELETE` | `/gebruikers/{id}` | Alleen beheerder. `actief`, `beheerder` |
| `POST` | `/gebruikers/{id}/wachtwoord-reset` | Alleen beheerder. Nieuw tijdelijk wachtwoord |
| `GET` | `/health` | Database en Ollama bereikbaar? |

## Ontwikkelen

```bash
make test   # backend-tests tegen Postgres; Ollama wordt nagebootst
make lint   # ruff en vue-tsc
```

De tests gebruiken een aparte database, `finkennis_test`, die ze zelf aanmaken. Zie
[CONTRIBUTING.md](CONTRIBUTING.md) voor de werkwijze.

## Licentie

FinKennis is open source onder de [European Union Public Licence 1.2](LICENSE).

Het NLDD Designsysteem, RijksSans, het rijkswapen en de huisstijlkleuren mogen alleen worden
gebruikt door de Rijksoverheid en partijen die in haar opdracht werken. Zie de
[NOTICES](https://github.com/NederlandseDigitaleDienst/design-system/blob/main/NOTICES.md) van
het designsysteem. Hergebruik je FinKennis buiten het Rijk, importeer dan
`@nldd/design-system/styles/system-font` in `frontend/src/main.ts` en vervang de favicon in
`frontend/public/`.
