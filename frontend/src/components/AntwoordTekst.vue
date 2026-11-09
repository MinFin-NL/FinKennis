<script setup lang="ts">
import { computed } from 'vue';
import LichteMarkdown from './LichteMarkdown.vue';

const props = defineProps<{ tekst: string }>();

// Denkt de assistent mee (eigen redenering, niet uit de documenten), dan begint dat op een
// regel met alleen 'Meedenken:' (zie MEEDENKEN in de backend). Alles daarna staat apart, zodat
// de lezer feiten uit de documenten niet verwart met de redenering van het model.
const MEEDENKEN = /^\s*\**\s*Meedenken:?\s*\**\s*$/im;

const delen = computed(() => {
  const m = MEEDENKEN.exec(props.tekst);
  if (!m) return { feiten: props.tekst, meedenken: '' };
  return {
    feiten: props.tekst.slice(0, m.index),
    meedenken: props.tekst.slice(m.index + m[0].length).trim(),
  };
});
</script>

<template>
  <nldd-container gap="12">
    <LichteMarkdown :tekst="delen.feiten" />
    <nldd-box v-if="delen.meedenken" background="tinted">
      <nldd-container padding="12" gap="8">
        <nldd-tag size="sm" color="paars" icon="message-rectangle-text" text="Meedenken · niet uit de documenten"></nldd-tag>
        <LichteMarkdown :tekst="delen.meedenken" />
      </nldd-container>
    </nldd-box>
  </nldd-container>
</template>
