<script setup lang="ts">
import { ref } from 'vue';

defineProps<{ bezig: boolean }>();
const emit = defineEmits<{ verstuur: [vraag: string]; stop: [] }>();

const vraag = ref('');
// Bij elke verzending een nieuwe sleutel, zodat het veld echt leeg begint.
const veldKey = ref(0);

function waarde(e: Event): string {
  return (e as CustomEvent).detail?.value ?? (e.target as HTMLTextAreaElement)?.value ?? '';
}

function verstuur() {
  const tekst = vraag.value.trim();
  if (!tekst) return;
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
  <nldd-container padding="16" gap="8">
    <nldd-form-field label="Je vraag" supporting-label="Enter verstuurt, Shift+Enter voor een nieuwe regel">
      <nldd-multi-line-text-field
        :key="veldKey"
        :value="vraag"
        rows="2"
        maxlength="4000"
        @input="vraag = waarde($event)"
        @keydown="toets"
      ></nldd-multi-line-text-field>
      <nldd-form-field-help-text>
        Antwoorden worden gemaakt door AI en kunnen fouten bevatten. Controleer ze in de bronnen.
      </nldd-form-field-help-text>
    </nldd-form-field>
    <nldd-container layout="row" horizontal-alignment="right" gap="8">
      <nldd-button v-if="bezig" appearance="secondary" text="Stop" @click="emit('stop')"></nldd-button>
      <nldd-button appearance="primary" start-icon="paper-plane" text="Verstuur" :loading="bezig" @click="verstuur"></nldd-button>
    </nldd-container>
  </nldd-container>
</template>
