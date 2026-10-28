<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue';
import { api, stelVraag, type Bericht, type Gesprek, type Kennisbank } from '../api';
import AntwoordTekst from './AntwoordTekst.vue';

const props = defineProps<{ kennisbank: Kennisbank }>();
const emit = defineEmits<{ naarDocumenten: [] }>();

const gesprekken = ref<Gesprek[]>([]);
const actief = ref<Gesprek | null>(null);
const berichten = ref<Bericht[]>([]);
const bezig = ref(false);
const fout = ref<string | null>(null);
let controller: AbortController | null = null;

async function laadGesprekken() {
  try {
    gesprekken.value = await api.gesprekken(props.kennisbank.id);
  } catch (e) {
    fout.value = (e as Error).message;
  }
}

async function open(g: Gesprek) {
  fout.value = null;
  const detail = await api.gesprek(g.id);
  actief.value = detail;
  berichten.value = detail.berichten;
  scrollNaarEinde();
}

function nieuw() {
  stop();
  actief.value = null;
  berichten.value = [];
  fout.value = null;
  laadGesprekken();
}

// Niet dit component scrolt maar de nldd-page eromheen. scrollIntoView zou het einde onder de
// sticky invoerbalk leggen; daarom de scroller van de pagina zelf helemaal naar beneden.
type Pagina = HTMLElement & { scrollTarget?: HTMLElement; scrollEventTarget?: EventTarget };
const wortel = ref<HTMLElement | null>(null);
function pagina(): Pagina | null {
  return (wortel.value?.closest('nldd-page') as Pagina | null) ?? null;
}
function scroller(): HTMLElement | null {
  return pagina()?.scrollTarget ?? null;
}

function scrollNaarEinde() {
  nextTick(() => {
    const s = scroller();
    if (s) s.scrollTop = s.scrollHeight;
  });
}

// Meescrollen met het antwoord tot de gebruiker zelf omhoog scrolt; wie weer helemaal
// onderaan komt, volgt weer. Een drempel ("dicht bij de bodem") werkt niet: een kleine
// scrollstap omhoog valt binnen de drempel en het volgende token trekt je terug.
let volg = true;
let vorigeTop = 0;
let vorigeHoogte = 0;
function opScroll() {
  const s = scroller();
  if (!s) return;
  // Krimpt de inhoud even, dan zakt scrollTop ook zonder dat iemand scrolt; dat telt niet.
  // Wie naar beneden scrolt, hoeft het groeiende antwoord niet tot op de pixel in te halen.
  const afstand = s.scrollHeight - s.scrollTop - s.clientHeight;
  const omhoog = s.scrollTop < vorigeTop - 1 && s.scrollHeight >= vorigeHoogte;
  if (omhoog) volg = false;
  else if (afstand < 8 || (s.scrollTop > vorigeTop && afstand < 64)) volg = true;
  vorigeTop = s.scrollTop;
  vorigeHoogte = s.scrollHeight;
}
// Wiel, toetsen en vegen stoppen het volgen meteen, nog voor het scroll-event: die scrollen
// vloeiend, dus de eerste stap is nog "onderaan" en het volgende token zou je terugtrekken.
function opWiel(e: WheelEvent) {
  if (e.deltaY < 0) volg = false;
}
const omhoogToetsen = new Set(['ArrowUp', 'PageUp', 'Home']);
function opToets(e: KeyboardEvent) {
  // In het invoerveld verplaatsen pijltjes de cursor, niet de pagina.
  if ((e.target as Element).closest?.('nldd-multi-line-text-field')) return;
  if (omhoogToetsen.has(e.key) || (e.key === ' ' && e.shiftKey)) volg = false;
}
let vingerY = 0;
function opAanraken(e: TouchEvent) {
  vingerY = e.touches[0]?.clientY ?? 0;
}
function opVegen(e: TouchEvent) {
  const y = e.touches[0]?.clientY ?? vingerY;
  if (y > vingerY) volg = false;
  vingerY = y;
}

// In smalle schermen scrolt het document in plaats van de pagina; daarom bij elke vraag
// opnieuw koppelen aan wat de pagina op dat moment als scroller opgeeft.
let gekoppeld: EventTarget | null = null;
function koppelScroll() {
  const doel = pagina()?.scrollEventTarget ?? null;
  if (doel === gekoppeld) return;
  gekoppeld?.removeEventListener('scroll', opScroll);
  doel?.addEventListener('scroll', opScroll, { passive: true });
  gekoppeld = doel;
}

async function verstuur(vraag: string) {
  if (bezig.value) return;
  fout.value = null;
  bezig.value = true;
  controller = new AbortController();
  try {
    if (!actief.value) {
      actief.value = await api.maakGesprek(props.kennisbank.id);
    }
    const nu = new Date().toISOString();
    berichten.value.push({ id: `v-${nu}`, rol: 'user', inhoud: vraag, bronnen: [], createdAt: nu });
    berichten.value.push({ id: `a-${nu}`, rol: 'assistant', inhoud: '', bronnen: [], createdAt: nu });
    // Via de reactieve array muteren, zodat Vue elke token ziet.
    const antwoord = berichten.value[berichten.value.length - 1];
    koppelScroll();
    volg = true;
    scrollNaarEinde();

    await stelVraag(
      actief.value.id,
      vraag,
      {
        bronnen: (b) => (antwoord.bronnen = b),
        token: (t) => {
          antwoord.inhoud += t;
          if (volg) scrollNaarEinde();
        },
      },
      controller.signal,
    );
  } catch (e) {
    if ((e as Error).name !== 'AbortError') fout.value = (e as Error).message;
  } finally {
    bezig.value = false;
    controller = null;
  }
}

function stop() {
  controller?.abort();
}

onMounted(() => {
  laadGesprekken();
  const p = pagina();
  p?.addEventListener('wheel', opWiel, { passive: true });
  window.addEventListener('keydown', opToets);
  p?.addEventListener('touchstart', opAanraken, { passive: true });
  p?.addEventListener('touchmove', opVegen, { passive: true });
});
onUnmounted(() => {
  const p = pagina();
  p?.removeEventListener('wheel', opWiel);
  window.removeEventListener('keydown', opToets);
  p?.removeEventListener('touchstart', opAanraken);
  p?.removeEventListener('touchmove', opVegen);
  gekoppeld?.removeEventListener('scroll', opScroll);
});
defineExpose({ actief, bezig, verstuur, stop });

// Alleen de bronnen waar het antwoord echt naar verwijst, zoals [2] of [1][3].
function geciteerd(b: Bericht) {
  const nummers = new Set([...b.inhoud.matchAll(/\[(\d+)\]/g)].map((m) => Number(m[1])));
  return b.bronnen.filter((bron) => nummers.has(bron.nummer));
}

function datum(iso: string) {
  return new Date(iso).toLocaleString('nl-NL', { dateStyle: 'medium', timeStyle: 'short' });
}
</script>

<template>
  <nldd-container ref="wortel" gap="24">
    <nldd-container layout="row" gap="8">
      <nldd-button
        v-if="actief"
        appearance="secondary"
        start-icon="plus"
        text="Nieuw gesprek"
        @click="nieuw"
      ></nldd-button>
    </nldd-container>

    <nldd-banner v-if="fout" variant="critical" text="Er ging iets mis" :supporting-text="fout" dismissible @dismiss="fout = null"></nldd-banner>

    <!-- Geen actief gesprek: uitleg en eerdere gesprekken -->
    <template v-if="!actief">
      <nldd-inline-dialog
        v-if="kennisbank.aantalDocumenten === 0"
        icon="upload-document"
        text="Deze kennisbank is nog leeg"
        supporting-text="Voeg eerst documenten toe. Daarna kun je er vragen over stellen."
      >
        <nldd-button slot="actions" appearance="primary" text="Documenten toevoegen" @click="emit('naarDocumenten')"></nldd-button>
      </nldd-inline-dialog>
      <nldd-inline-dialog
        v-else
        icon="sparkles"
        text="Stel een vraag over de documenten"
        supporting-text="De assistent zoekt het antwoord op in deze kennisbank en noemt de bronnen. Controleer belangrijke antwoorden altijd in het document zelf."
      ></nldd-inline-dialog>

      <nldd-container v-if="gesprekken.length" gap="8">
        <nldd-title size="5" heading-level="2" text="Eerdere gesprekken"></nldd-title>
        <nldd-list appearance="box-base" accessible-label="Eerdere gesprekken">
          <nldd-list-item v-for="g in gesprekken" :key="g.id" button @click="open(g)">
            <nldd-icon-cell icon="message-rectangle-text"></nldd-icon-cell>
            <nldd-spacer-cell size="8"></nldd-spacer-cell>
            <nldd-text-cell :text="g.titel" :supporting-text="datum(g.createdAt)"></nldd-text-cell>
            <nldd-spacer-cell size="12"></nldd-spacer-cell>
            <nldd-icon-cell size="20" color="secondary" icon="chevron-right"></nldd-icon-cell>
          </nldd-list-item>
        </nldd-list>
      </nldd-container>
    </template>

    <!-- Het gesprek -->
    <nldd-container v-else gap="24" role="log" aria-live="polite" aria-label="Gesprek">
      <template v-for="(b, i) in berichten" :key="b.id">
        <!-- NLDD-containers hebben size containment en krimpen niet tot hun tekst; daarom een
             vraag als blok over de volle breedte. -->
        <nldd-box v-if="b.rol === 'user'" background="accent-tinted">
          <nldd-container padding="12"><span class="vraag-tekst">{{ b.inhoud }}</span></nldd-container>
        </nldd-box>
        <nldd-container v-else gap="12">
          <nldd-activity-indicator v-if="!b.inhoud && bezig" size="24" text="Antwoord wordt gemaakt" show-text></nldd-activity-indicator>
          <AntwoordTekst :tekst="b.inhoud" />
          <nldd-container v-if="!(bezig && i === berichten.length - 1) && geciteerd(b).length" gap="8">
            <nldd-text size="sm" color="secondary">Bronnen</nldd-text>
            <nldd-list appearance="box-tinted" accessible-label="Bronnen bij dit antwoord">
              <nldd-list-item v-for="bron in geciteerd(b)" :key="bron.nummer" size="sm">
                <nldd-text-cell width="fit-content" :text="`[${bron.nummer}]`" vertical-alignment="top"></nldd-text-cell>
                <nldd-spacer-cell size="8"></nldd-spacer-cell>
                <nldd-text-cell
                  :text="bron.bestandsnaam + (bron.pagina ? `, pagina ${bron.pagina}` : '') + (bron.kopjes.length ? ` — ${bron.kopjes.join(' › ')}` : '')"
                  :supporting-text="bron.fragment.length >= 400 ? bron.fragment + '…' : bron.fragment"
                ></nldd-text-cell>
              </nldd-list-item>
            </nldd-list>
          </nldd-container>
        </nldd-container>
      </template>
    </nldd-container>
  </nldd-container>
</template>

<style scoped>
.vraag-tekst {
  white-space: pre-line;
}
</style>
