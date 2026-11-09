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

const secties = computed(() => {
  const s = props.inzichten;
  return s?.sectiesTotaal ? `${s.sectiesKlaar} van ${s.sectiesTotaal} secties gelezen` : null;
});

// Zolang niet alle documenten helemaal gelezen zijn, tellen die nog niet mee in wat opvalt.
const voortgangTekst = computed(() => {
  const s = props.inzichten;
  if (!s?.documentenOnderweg) return null;
  const docs = s.documentenOnderweg === 1 ? '1 document' : `${s.documentenOnderweg} documenten`;
  return `${docs} ${s.documentenOnderweg === 1 ? 'wordt' : 'worden'} nog helemaal gelezen${secties.value ? ` (${secties.value})` : ''}; wat daarin opvalt, telt nog niet mee.`;
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
    <nldd-container v-if="voortgangTekst" layout="row" gap="8" vertical-alignment="center">
      <nldd-activity-indicator size="16"></nldd-activity-indicator>
      <nldd-text size="sm" color="secondary">{{ voortgangTekst }}</nldd-text>
    </nldd-container>
    <nldd-form-field
      :label="vervolg ? 'Praat verder of stel een nieuwe vraag' : 'Je vraag'"
      supporting-label="Feiten uit de documenten krijgen een bron. Vraag je waarom of wat iets betekent, dan denkt de assistent ook mee; dat staat apart."
    >
      <nldd-multi-line-text-field
        :key="veldKey"
        :value="vraag"
        rows="2"
        maxlength="4000"
        @input="vraag = waarde($event)"
        @keydown="toets"
      ></nldd-multi-line-text-field>
      <nldd-form-field-help-text>
        Enter verstuurt, Shift+Enter voor een nieuwe regel. Antwoorden worden gemaakt door AI en
        kunnen fouten bevatten. Controleer ze in de bronnen.
      </nldd-form-field-help-text>
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
