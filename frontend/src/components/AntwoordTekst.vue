<script setup lang="ts">
import { computed } from 'vue';

// Het taalmodel schrijft lichte Markdown. We tonen alinea's en opsommingen, zonder v-html:
// modeluitvoer komt nooit als HTML in de pagina.
const props = defineProps<{ tekst: string }>();

type Blok = { soort: 'p'; tekst: string } | { soort: 'ul' | 'ol'; items: string[] };

const UL = /^\s*[-*•]\s+/;
const OL = /^\s*\d+[.)]\s+/;
// Een kopje (### Thema) tonen we als vetgedrukte regel.
const KOP = /^\s*#{1,6}\s+(.*)$/;

const blokken = computed<Blok[]>(() => {
  const resultaat: Blok[] = [];
  for (const deel of props.tekst.split(/\n\s*\n/)) {
    // Binnen een alinea kunnen een kopje en een opsomming direct op elkaar volgen.
    // Opeenvolgende regels van dezelfde soort vormen samen een blok; een kopje staat apart.
    let huidig = null as Blok | null;
    for (const r of deel.split('\n').filter((r) => r.trim())) {
      const kop = r.match(KOP);
      if (kop) {
        resultaat.push({ soort: 'p', tekst: `**${kop[1].replace(/\*\*/g, '')}**` });
        huidig = null;
        continue;
      }
      const soort = UL.test(r) ? 'ul' : OL.test(r) ? 'ol' : 'p';
      if (soort === 'p') {
        if (huidig?.soort === 'p') huidig.tekst += '\n' + r;
        else resultaat.push((huidig = { soort: 'p', tekst: r }));
      } else {
        const item = r.replace(soort === 'ul' ? UL : OL, '');
        if (huidig?.soort === soort) huidig.items.push(item);
        else resultaat.push((huidig = { soort, items: [item] }));
      }
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
