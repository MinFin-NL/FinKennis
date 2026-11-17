<script setup lang="ts">
import { computed, ref } from 'vue';
import type { InzichtenStatus } from '../api';

const props = defineProps<{ bezig: boolean; vervolg: boolean; inzichten: InzichtenStatus | null }>();
const emit = defineEmits<{ verstuur: [vraag: string]; stop: [] }>();

// Er is één manier van vragen. Deze voorbeelden maken zichtbaar dat je ook kunt vragen wat er
// opvalt over de documenten heen (daarvoor zijn de inzichten), niet alleen naar feiten.
const SUGGESTIES = [
  'Wat valt op over de documenten heen?',
  "Welke risico's komen in meer documenten terug?",
  'Waar spreken de documenten elkaar tegen?',
];

// Zolang niet alle documenten helemaal gelezen zijn, tellen die nog niet mee in wat opvalt.
// De gebruiker ziet documenten, geen secties: dat is een intern getal. De secties maken de
// balk alleen vloeiend, zodat hij ook beweegt terwijl één groot document gelezen wordt.
const voortgang = computed(() => {
  const s = props.inzichten;
  if (!s?.documentenOnderweg) return null;
  const totaal = s.documentenKlaar + s.documentenOnderweg + s.documentenMislukt;
  const deel = s.sectiesTotaal ? s.sectiesKlaar / s.sectiesTotaal : 0;
  return {
    totaal,
    waarde: s.documentenKlaar + s.documentenMislukt + s.documentenOnderweg * deel,
    tekst: `${s.documentenKlaar} van ${totaal} documenten`,
  };
});

const vraag = ref('');
// Bij elke verzending een nieuwe sleutel, zodat het veld echt leeg begint.
const veldKey = ref(0);

function waarde(e: Event): string {
  return (e as CustomEvent).detail?.value ?? (e.target as HTMLTextAreaElement)?.value ?? '';
}

function verstuur(tekst = vraag.value.trim()) {
  if (!tekst || props.bezig) return;
  emit('verstuur', tekst);
  vraag.value = '';
  veldKey.value++;
}

function toets(e: KeyboardEvent) {
  // Enter verstuurt, Shift+Enter maakt een nieuwe regel.
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    verstuur();
  }
}
</script>

<template>
  <nldd-container class="chat-invoer" padding="16" gap="8">
    <nldd-container v-if="!vervolg" layout="wrap" gap="8">
      <nldd-button
        v-for="s in SUGGESTIES"
        :key="s"
        appearance="neutral-tinted"
        size="sm"
        start-icon="sparkles"
        :text="s"
        @click="verstuur(s)"
      ></nldd-button>
    </nldd-container>
    <!-- Direct onder de voorbeeldvragen: juist die hangen af van de inzichten. -->
    <nldd-progress-bar
      v-if="voortgang"
      size="sm"
      text="Inzichten worden voorbereid. Vragen stellen kan al."
      :max="voortgang.totaal"
      :value="voortgang.waarde"
      :value-text="voortgang.tekst"
      :accessible-label="`Inzichten voorbereiden: ${voortgang.tekst} gelezen`"
    ></nldd-progress-bar>
    <!-- Weinig uitleg rond het veld: hoe het antwoord in elkaar zit (bronnen, meedenken) laat
         het antwoord zelf zien, en Enter om te versturen verwacht iedereen al van een chat. -->
    <nldd-form-field :label="vervolg ? 'Praat verder of stel een nieuwe vraag' : 'Je vraag'">
      <nldd-multi-line-text-field
        :key="veldKey"
        :value="vraag"
        rows="2"
        maxlength="4000"
        :placeholder="vervolg ? 'Vraag verder…' : 'Stel een vraag over de documenten…'"
        @input="vraag = waarde($event)"
        @keydown="toets"
      ></nldd-multi-line-text-field>
      <nldd-form-field-help-text>Gemaakt door AI, kan fouten bevatten. Controleer de bronnen.</nldd-form-field-help-text>
    </nldd-form-field>
    <nldd-container layout="row" horizontal-alignment="right" gap="8">
      <nldd-button v-if="bezig" appearance="secondary" text="Stop" @click="emit('stop')"></nldd-button>
      <nldd-button appearance="primary" start-icon="paper-plane" text="Verstuur" :loading="bezig" @click="verstuur"></nldd-button>
    </nldd-container>
  </nldd-container>
</template>

<style scoped>
/* De sticky footer van nldd-page is maar 95% dekkend; daardoor schemert het antwoord erdoorheen. */
.chat-invoer {
  background-color: var(--context-parent-background-color, var(--semantics-surfaces-base-background-color));
}
</style>
