<script setup lang="ts">
import { computed } from 'vue';

// Het taalmodel schrijft lichte Markdown. We tonen alinea's en opsommingen, zonder v-html:
// modeluitvoer komt nooit als HTML in de pagina.
const props = defineProps<{ tekst: string }>();

type Blok = { soort: 'p'; tekst: string } | { soort: 'ul' | 'ol'; items: string[] };

const blokken = computed<Blok[]>(() => {
  const resultaat: Blok[] = [];
  for (const deel of props.tekst.split(/\n\s*\n/)) {
    const regels = deel.split('\n').filter((r) => r.trim());
    if (!regels.length) continue;
    if (regels.every((r) => /^\s*[-*•]\s+/.test(r))) {
      resultaat.push({ soort: 'ul', items: regels.map((r) => r.replace(/^\s*[-*•]\s+/, '')) });
    } else if (regels.every((r) => /^\s*\d+[.)]\s+/.test(r))) {
      resultaat.push({ soort: 'ol', items: regels.map((r) => r.replace(/^\s*\d+[.)]\s+/, '')) });
    } else {
      resultaat.push({ soort: 'p', tekst: regels.join('\n') });
    }
  }
  return resultaat;
});

// **vet** omzetten naar segmenten
function segmenten(tekst: string) {
  return tekst.split(/(\*\*[^*]+\*\*)/).map((s) =>
    s.startsWith('**') && s.endsWith('**') ? { vet: true, s: s.slice(2, -2) } : { vet: false, s },
  );
}
</script>

<template>
  <nldd-rich-text v-if="blokken.length">
    <template v-for="(blok, i) in blokken" :key="i">
      <p v-if="blok.soort === 'p'" class="antwoord-alinea">
        <template v-for="(seg, j) in segmenten(blok.tekst)" :key="j"><strong v-if="seg.vet">{{ seg.s }}</strong><template v-else>{{ seg.s }}</template></template>
      </p>
      <component :is="blok.soort" v-else>
        <li v-for="(item, j) in blok.items" :key="j">
          <template v-for="(seg, k) in segmenten(item)" :key="k"><strong v-if="seg.vet">{{ seg.s }}</strong><template v-else>{{ seg.s }}</template></template>
        </li>
      </component>
    </template>
  </nldd-rich-text>
</template>

<style scoped>
.antwoord-alinea {
  white-space: pre-line;
}
</style>
