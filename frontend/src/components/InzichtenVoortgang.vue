<script setup lang="ts">
import { computed } from 'vue';
import type { InzichtenStatus } from '../api';

const props = defineProps<{ status: InzichtenStatus | null }>();

// Zolang niet alle documenten helemaal gelezen zijn, tellen die nog niet mee in wat opvalt.
// De gebruiker ziet documenten, geen secties: dat is een intern getal. De secties maken de
// balk alleen vloeiend, zodat hij ook beweegt terwijl één groot document gelezen wordt.
const voortgang = computed(() => {
  const s = props.status;
  if (!s?.documentenOnderweg) return null;
  const totaal = s.documentenKlaar + s.documentenOnderweg + s.documentenMislukt;
  const deel = s.sectiesTotaal ? s.sectiesKlaar / s.sectiesTotaal : 0;
  return {
    totaal,
    waarde: s.documentenKlaar + s.documentenMislukt + s.documentenOnderweg * deel,
    tekst: `${s.documentenKlaar} van ${totaal} documenten`,
  };
});
</script>

<template>
  <nldd-progress-bar
    v-if="voortgang"
    size="sm"
    text="Inzichten worden voorbereid. Vragen stellen kan al."
    :max="voortgang.totaal"
    :value="voortgang.waarde"
    :value-text="voortgang.tekst"
    :accessible-label="`Inzichten voorbereiden: ${voortgang.tekst} gelezen`"
  ></nldd-progress-bar>
</template>
