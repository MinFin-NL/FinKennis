<script setup lang="ts">
import { ref } from 'vue';
import type { InzichtenStatus } from '../api';
import InzichtenVoortgang from './InzichtenVoortgang.vue';

// De voorbeeldvragen en de voortgang staan bij een nieuw gesprek bovenaan in ChatTab, bij de
// uitleg. Hier, in de sticky balk, alleen wat je tijdens een gesprek nodig hebt; hoe lager
// deze balk, hoe meer van het gesprek zichtbaar blijft.
const props = defineProps<{ bezig: boolean; vervolg: boolean; inzichten: InzichtenStatus | null }>();
const emit = defineEmits<{ verstuur: [vraag: string]; stop: [] }>();

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
    <InzichtenVoortgang v-if="vervolg" :status="inzichten" />
    <!-- Geen zichtbaar label: de placeholder zegt wat het veld is, de schermlezer krijgt het
         label via accessible-label. Versturen staat ernaast, zoals in elke chat. -->
    <div class="veld-rij">
      <nldd-multi-line-text-field
        :key="veldKey"
        :value="vraag"
        rows="2"
        maxlength="4000"
        :accessible-label="vervolg ? 'Praat verder of stel een nieuwe vraag' : 'Je vraag'"
        :placeholder="vervolg ? 'Vraag verder…' : 'Stel een vraag over de documenten…'"
        @input="vraag = waarde($event)"
        @keydown="toets"
      ></nldd-multi-line-text-field>
      <nldd-button v-if="bezig" appearance="secondary" text="Stop" @click="emit('stop')"></nldd-button>
      <nldd-button v-else appearance="primary" start-icon="paper-plane" text="Verstuur" @click="verstuur()"></nldd-button>
    </div>
    <nldd-text size="sm" color="secondary">Gemaakt door AI, kan fouten bevatten. Controleer de bronnen.</nldd-text>
  </nldd-container>
</template>

<style scoped>
/* De sticky footer van nldd-page is maar 95% dekkend; daardoor schemert het antwoord erdoorheen. */
.chat-invoer {
  background-color: var(--context-parent-background-color, var(--semantics-surfaces-base-background-color));
}

.veld-rij {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: end;
  gap: 8px;
}
</style>
