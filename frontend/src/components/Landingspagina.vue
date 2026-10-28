<script setup lang="ts">
import { ref } from 'vue';
import { login } from '../auth';
// Het designsysteem tekent het Rijkslogo alleen in zijn eigen navigatiebalk en exporteert het
// beeldmerk niet los; daarom een lokale kopie, net als in de invulhulp.
import rijkslogoUrl from '../assets/rijkslogo.svg';

const bezig = ref(false);

async function inloggen() {
  bezig.value = true;
  await login();
}

const kenmerken = [
  {
    icon: 'books-vertical',
    titel: 'Eigen kennisbanken',
    tekst:
      'Bundel beleidsstukken, handleidingen en regelingen per onderwerp. Upload PDF, Word, PowerPoint, Excel, ODT, HTML, Markdown of tekst; FinKennis leest kopjes, tabellen en pagina’s mee.',
  },
  {
    icon: 'text-quote',
    titel: 'Antwoorden met bronnen',
    tekst:
      'Stel je vraag in gewone taal. Elk antwoord verwijst naar bestand, pagina en kopje, zodat je het direct in het brondocument controleert. Ook een exact artikelnummer vind je terug.',
  },
  {
    icon: 'shield-lock',
    titel: 'Blijft binnen de deur',
    tekst:
      'Het taalmodel draait op eigen servers: documenten gaan niet naar een externe AI-dienst. Je kennisbanken en gesprekken zijn alleen voor jou zichtbaar.',
  },
];
</script>

<template>
  <div class="landing">
    <nldd-status-bar
      variant="warning"
      text="Dit is een bètaversie van dit hulpmiddel. Vragen of feedback? innovatiemanagementfinancien@minfin.nl"
      href="mailto:innovatiemanagementfinancien@minfin.nl"
    ></nldd-status-bar>

    <main>
      <section class="hero">
        <div class="hero__aurora" aria-hidden="true"></div>
        <div class="hero__inner">
          <div class="merk">
            <img class="merk__embleem" :src="rijkslogoUrl" alt="" />
            <span class="merk__org">Ministerie van Financiën</span>
          </div>

          <h1 class="hero__titel">Fin<span class="hero__accent">Kennis</span></h1>
          <p class="hero__tagline">Stel vragen aan je eigen documenten</p>
          <p class="hero__lead">
            Maak een kennisbank, voeg je documenten toe en vraag wat je wilt weten. FinKennis zoekt
            de passages die ertoe doen en geeft een antwoord met bronverwijzing. Jij controleert,
            de assistent zoekt.
          </p>

          <div class="hero__cta">
            <nldd-button
              class="cta"
              appearance="inherit-filled"
              size="lg"
              start-icon="arrow-right-in-bucket"
              text="Inloggen met SSO"
              :loading="bezig"
              @click="inloggen"
            ></nldd-button>
            <span class="hero__noot">Inloggen vereist · alleen voor medewerkers van het ministerie</span>
          </div>
        </div>
      </section>

      <section class="kenmerken" aria-label="Wat FinKennis voor je doet">
        <article v-for="k in kenmerken" :key="k.titel" class="kenmerk">
          <span class="kenmerk__icoon"><nldd-icon :icon="k.icon" size="28" color="accent"></nldd-icon></span>
          <h2 class="kenmerk__titel">{{ k.titel }}</h2>
          <p class="kenmerk__tekst">{{ k.tekst }}</p>
        </article>
      </section>

      <p class="disclaimer">
        Antwoorden worden gemaakt door een taalmodel en kunnen fouten bevatten. Controleer
        belangrijke antwoorden in het brondocument.
      </p>
    </main>
  </div>
</template>

<style>
/* Buiten nldd-shell is er geen reset voor body; zonder dit staat er een witte rand omheen. */
body:has(.landing) {
  margin: 0;
}
</style>

<style scoped>
.landing {
  min-block-size: 100vh;
  font-family: var(--primitives-font-family-body);
  background: var(--semantics-surfaces-tinted-background-color);
}

/* Altijd donker accent met witte tekst, ook in dark mode: daar wordt de accentkleur zelf
   licht en zou de witte tekst wegvallen. */
.hero {
  position: relative;
  overflow: hidden;
  background: #154273; /* lintblauw, de kleur van het Rijkslogo */
  color: #fff;
  padding-block: clamp(3rem, 9vw, 6rem) clamp(3.5rem, 10vw, 6.5rem);
  padding-inline: var(--primitives-space-32);
}

/* Een langzaam bewegend noorderlicht achter de titel, zoals in de invulhulp. */
.hero__aurora {
  position: absolute;
  inset: -40% -10% auto -10%;
  block-size: 160%;
  background:
    radial-gradient(40% 50% at 18% 30%, rgb(14 165 233 / 0.55), transparent 70%),
    radial-gradient(45% 55% at 82% 25%, rgb(91 33 182 / 0.55), transparent 70%),
    radial-gradient(50% 60% at 55% 80%, rgb(14 165 233 / 0.35), transparent 70%);
  filter: blur(8px);
  opacity: 0.85;
  animation: aurora 18s ease-in-out infinite alternate;
  pointer-events: none;
}

@keyframes aurora {
  0% {
    transform: translate3d(-3%, -2%, 0) scale(1);
  }
  50% {
    transform: translate3d(3%, 2%, 0) scale(1.08);
  }
  100% {
    transform: translate3d(-2%, 1%, 0) scale(1.04);
  }
}

.hero__inner {
  position: relative;
  z-index: 1;
  max-inline-size: 46rem;
  margin-inline: auto;
  text-align: center;
}

.merk {
  display: inline-flex;
  align-items: center;
  gap: var(--primitives-space-12);
  padding: var(--primitives-space-4) var(--primitives-space-16);
  margin-block-end: var(--primitives-space-24);
  background: rgb(255 255 255 / 0.1);
  border: 1px solid rgb(255 255 255 / 0.18);
  border-radius: 999px;
}

/* Het Rijkslogo is staand (1:2): hoogte zetten, breedte volgt. */
.merk__embleem {
  block-size: 2rem;
  inline-size: auto;
}

.merk__org {
  font-size: var(--primitives-font-size-90);
  font-weight: var(--primitives-font-weight-body-semi-bold);
  color: rgb(255 255 255 / 0.92);
  white-space: nowrap;
}

.hero__titel {
  margin: 0;
  font-size: clamp(3rem, 11vw, 5.5rem);
  font-weight: var(--primitives-font-weight-body-bold);
  line-height: 1.02;
  letter-spacing: -0.02em;
  color: #fff;
}

.hero__accent {
  background: linear-gradient(110deg, #7dd3fc 0%, #a78bfa 45%, #7dd3fc 100%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
  animation: glans 6s linear infinite;
}

@keyframes glans {
  to {
    background-position: 200% center;
  }
}

@media (prefers-reduced-motion: reduce) {
  .hero__aurora,
  .hero__accent {
    animation: none;
  }
}

.hero__tagline {
  margin: var(--primitives-space-16) auto 0;
  max-inline-size: 36rem;
  font-size: clamp(1.125rem, 2.4vw, 1.5rem);
  font-weight: var(--primitives-font-weight-body-semi-bold);
  color: rgb(255 255 255 / 0.95);
}

.hero__lead {
  margin: var(--primitives-space-16) auto 0;
  max-inline-size: 38rem;
  font-size: var(--primitives-font-size-100);
  line-height: var(--primitives-line-height-loose);
  color: rgb(255 255 255 / 0.8);
}

.hero__cta {
  margin-block-start: var(--primitives-space-40);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--primitives-space-12);
}

/* inherit-filled neemt de tekstkleur over: wit op de accentkleur. */
.cta {
  border-radius: var(--primitives-corner-radius-md);
  box-shadow: 0 6px 20px rgb(0 0 0 / 0.25);
}

.hero__noot {
  font-size: var(--primitives-font-size-90);
  color: rgb(255 255 255 / 0.65);
}

.kenmerken {
  position: relative;
  z-index: 2;
  max-inline-size: 64rem;
  margin: clamp(-3rem, -6vw, -4rem) auto 0;
  padding-inline: var(--primitives-space-32);
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr));
  gap: var(--primitives-space-24);
}

.kenmerk {
  background: var(--semantics-surfaces-base-background-color);
  border: 1px solid var(--semantics-dividers-color);
  border-radius: var(--primitives-corner-radius-md);
  padding: var(--primitives-space-32) var(--primitives-space-24);
  box-shadow: var(--primitives-box-shadows-level-2);
  transition:
    transform 150ms,
    box-shadow 150ms;
}

.kenmerk:hover {
  transform: translateY(-3px);
  box-shadow: var(--primitives-box-shadows-level-3);
}

.kenmerk__icoon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  inline-size: 3rem;
  block-size: 3rem;
  margin-block-end: var(--primitives-space-16);
  background: var(--semantics-surfaces-tinted-background-color);
  border-radius: var(--primitives-corner-radius-sm);
}

.kenmerk__titel {
  margin: 0 0 var(--primitives-space-8);
  font-size: var(--primitives-font-size-200);
  font-weight: var(--primitives-font-weight-body-bold);
  color: var(--semantics-content-accent-color);
}

.kenmerk__tekst {
  margin: 0;
  font-size: var(--primitives-font-size-90);
  line-height: var(--primitives-line-height-snug);
  color: var(--semantics-content-secondary-color);
}

.disclaimer {
  max-inline-size: 40rem;
  margin: 0 auto;
  padding: var(--primitives-space-40) var(--primitives-space-32) var(--primitives-space-64);
  text-align: center;
  font-size: var(--primitives-font-size-90);
  color: var(--semantics-content-secondary-color);
}
</style>
