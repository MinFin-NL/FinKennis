<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { api, type Inzicht, type KbDocument, type Kennisbank } from '../api';

const props = defineProps<{ open: boolean; kennisbank: Kennisbank; document: KbDocument | null }>();
const emit = defineEmits<{ close: []; gewijzigd: [doc: KbDocument] }>();

const inzichten = ref<Inzicht[]>([]);
const laden = ref(false);
const bezig = ref(false);
const fout = ref<string | null>(null);

const SOORT: Record<string, string> = {
  cijfer: 'Cijfer',
  risico: 'Risico',
  besluit: 'Besluit',
  afwijking: 'Afwijking',
  tegenstrijdigheid: 'Tegenstrijdigheid',
  overig: 'Overig',
};

const onderweg = computed(
  () => props.document?.inzichtenStatus === 'wachtrij' || props.document?.inzichtenStatus === 'verwerken',
);

async function laad() {
  if (!props.document) return;
  laden.value = true;
  fout.value = null;
  try {
    inzichten.value = await api.inzichten(props.kennisbank.id, props.document.id);
  } catch (e) {
    fout.value = (e as Error).message;
  } finally {
    laden.value = false;
  }
}

// De sheet blijft in de DOM; bij openen, en als de inzichten klaar komen, opnieuw laden.
watch(
  () => [props.open, props.document?.id, props.document?.inzichtenStatus] as const,
  ([open]) => {
    if (open) laad();
  },
);

async function opnieuw() {
  if (!props.document) return;
  bezig.value = true;
  fout.value = null;
  try {
    emit('gewijzigd', await api.maakInzichtenOpnieuw(props.kennisbank.id, props.document.id));
  } catch (e) {
    fout.value = (e as Error).message;
  } finally {
    bezig.value = false;
  }
}

function bron(i: Inzicht) {
  const paginas = [...new Set(i.bronnen.map((b) => b.pagina).filter((p) => p != null))];
  const plek = paginas.length ? `pagina ${paginas.join(', ')}` : '';
  return [SOORT[i.soort] ?? i.soort, i.thema, plek].filter(Boolean).join(' · ');
}
</script>

<template>
  <nldd-sheet placement="right" width="560px" :open="open" @close="emit('close')">
    <nldd-page>
      <nldd-top-title-bar
        slot="header"
        text="Inzichten"
        dismiss-text="Sluit"
        collapse-anchor="inzichten-sheet-titel"
        @dismiss="emit('close')"
      ></nldd-top-title-bar>
      <nldd-simple-section>
        <nldd-title
          id="inzichten-sheet-titel"
          slot="header"
          size="2"
          heading-level="1"
          :text="document?.bestandsnaam ?? 'Inzichten'"
        ></nldd-title>
        <nldd-container gap="16">
          <nldd-text color="secondary">
            Het taalmodel heeft dit document helemaal gelezen en hieruit gehaald wat opvalt, het
            belangrijkste eerst. Controleer een inzicht altijd in de genoemde pagina's.
          </nldd-text>

          <nldd-banner v-if="fout" variant="critical" text="Er ging iets mis" :supporting-text="fout"></nldd-banner>
          <nldd-banner
            v-if="document?.inzichtenStatus === 'fout'"
            variant="critical"
            text="Inzichten maken is mislukt"
            :supporting-text="document.inzichtenFoutmelding ?? undefined"
          ></nldd-banner>
          <nldd-banner
            v-if="onderweg"
            variant="accent"
            :text="
              document?.inzichtenStatus === 'verwerken'
                ? document.inzichtenSectiesTotaal
                  ? `De inzichten worden nu gemaakt: ${document.inzichtenSectiesKlaar} van ${document.inzichtenSectiesTotaal} secties gelezen`
                  : 'De inzichten worden nu gemaakt'
                : 'De inzichten staan in de wachtrij'
            "
            :supporting-text="
              document?.inzichtenStatus === 'verwerken'
                ? 'Het taalmodel leest het hele document, sectie voor sectie. Deze lijst werkt zichzelf bij zodra het klaar is.'
                : 'Kleine documenten gaan eerst. Bij een lokaal taalmodel kan het wachten op grote documenten lang duren. Deze lijst werkt zichzelf bij.'
            "
          ></nldd-banner>

          <nldd-activity-indicator v-if="laden && !inzichten.length" size="24" text="Inzichten laden" show-text></nldd-activity-indicator>

          <nldd-list v-if="inzichten.length" appearance="box-base" accessible-label="Inzichten">
            <nldd-list-item v-for="i in inzichten" :key="i.id">
              <nldd-text-cell :text="i.tekst" :supporting-text="bron(i)"></nldd-text-cell>
              <nldd-spacer-cell v-if="i.belang === 3" size="8"></nldd-spacer-cell>
              <nldd-cell v-if="i.belang === 3" vertical-alignment="top">
                <nldd-badge size="sm" color="accent" text="Belangrijk"></nldd-badge>
              </nldd-cell>
            </nldd-list-item>
          </nldd-list>
          <nldd-inline-dialog
            v-else-if="!laden && document?.inzichtenStatus === 'gereed'"
            icon="lightbulb"
            text="Geen inzichten gevonden"
            supporting-text="Het taalmodel vond niets opvallends in dit document. Je kunt het opnieuw laten proberen."
          ></nldd-inline-dialog>

          <nldd-container layout="row">
            <nldd-button
              appearance="secondary"
              start-icon="refresh"
              text="Inzichten opnieuw maken"
              :loading="bezig"
              :disabled="onderweg || document?.status !== 'gereed'"
              @click="opnieuw"
            ></nldd-button>
          </nldd-container>
        </nldd-container>
      </nldd-simple-section>
    </nldd-page>
  </nldd-sheet>
</template>
