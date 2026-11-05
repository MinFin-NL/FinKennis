<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { api, type DocumentStatus, type KbDocument, type Kennisbank } from '../api';
import BevestigDialog from './BevestigDialog.vue';
import InzichtenSheet from './InzichtenSheet.vue';

const props = defineProps<{ kennisbank: Kennisbank }>();
const emit = defineEmits<{ gewijzigd: [aantal: number] }>();

const ACCEPT = '.pdf,.docx,.pptx,.xlsx,.odt,.html,.htm,.md,.markdown,.txt,.csv';

const documenten = ref<KbDocument[]>([]);
const gekozen = ref<File[]>([]);
const veldKey = ref(0);
const bezig = ref(false);
const melding = ref<{ variant: 'success' | 'warning' | 'critical'; text: string; supporting?: string } | null>(
  null,
);
const teVerwijderen = ref<KbDocument | null>(null);
// Het id, niet het document: zo ziet de sheet de bijgewerkte status uit de lijst.
const inzichtenVan = ref<string | null>(null);
const inzichtenDoc = computed(() => documenten.value.find((d) => d.id === inzichtenVan.value) ?? null);
let timer: number | undefined;

const STATUS: Record<DocumentStatus, { tekst: string; kleur: string }> = {
  wachtrij: { tekst: 'In de wachtrij', kleur: 'neutral' },
  verwerken: { tekst: 'Wordt verwerkt', kleur: 'accent' },
  gereed: { tekst: 'Klaar', kleur: 'success' },
  fout: { tekst: 'Mislukt', kleur: 'critical' },
};

const ICOON: Record<string, string> = {
  pdf: 'pdf-document',
  md: 'markdown-document',
  markdown: 'markdown-document',
  odt: 'odt-document',
  txt: 'text-document',
};

const bezigeStatus = (s: DocumentStatus) => s === 'wachtrij' || s === 'verwerken';
const inBehandeling = computed(() => documenten.value.some((d) => bezigeStatus(d.status)));
// Na het verwerken worden de inzichten gemaakt; dat duurt langer, dus rustiger bijwerken.
const inzichtenOnderweg = computed(() =>
  documenten.value.some((d) => d.status === 'gereed' && bezigeStatus(d.inzichtenStatus)),
);

async function laad() {
  try {
    documenten.value = await api.documenten(props.kennisbank.id);
    emit('gewijzigd', documenten.value.length);
  } catch (e) {
    melding.value = { variant: 'critical', text: 'Documenten laden mislukt', supporting: (e as Error).message };
  }
  // Zolang er iets verwerkt wordt, de status elke 2 seconden bijwerken.
  window.clearTimeout(timer);
  if (inBehandeling.value) timer = window.setTimeout(laad, 2000);
  else if (inzichtenOnderweg.value) timer = window.setTimeout(laad, 5000);
}

function kies(e: Event) {
  gekozen.value = (e as CustomEvent).detail?.files ?? [];
}

async function upload() {
  if (!gekozen.value.length) {
    melding.value = { variant: 'warning', text: 'Kies eerst een of meer bestanden.' };
    return;
  }
  bezig.value = true;
  melding.value = null;
  try {
    const r = await api.upload(props.kennisbank.id, gekozen.value);
    const n = r.toegevoegd.length;
    melding.value = {
      variant: r.overgeslagen.length ? 'warning' : 'success',
      text: n === 1 ? '1 document toegevoegd' : `${n} documenten toegevoegd`,
      supporting: r.overgeslagen.length
        ? `Al aanwezig en overgeslagen: ${r.overgeslagen.join(', ')}.`
        : 'De documenten worden nu verwerkt. Daarna kun je er vragen over stellen.',
    };
    gekozen.value = [];
    veldKey.value++;
    await laad();
  } catch (e) {
    melding.value = { variant: 'critical', text: 'Uploaden mislukt', supporting: (e as Error).message };
  } finally {
    bezig.value = false;
  }
}

async function verwijder() {
  const doc = teVerwijderen.value;
  if (!doc) return;
  try {
    await api.verwijderDocument(props.kennisbank.id, doc.id);
    await laad();
  } catch (e) {
    melding.value = { variant: 'critical', text: 'Verwijderen mislukt', supporting: (e as Error).message };
  }
}

function icoon(naam: string) {
  return ICOON[naam.split('.').pop()?.toLowerCase() ?? ''] ?? 'document';
}

function omschrijving(d: KbDocument) {
  if (d.status === 'fout') return d.foutmelding ?? 'Onbekende fout';
  const kb = d.grootte < 1024 * 1024 ? `${Math.ceil(d.grootte / 1024)} kB` : `${(d.grootte / 1024 / 1024).toFixed(1)} MB`;
  return d.status === 'gereed' ? `${kb} · ${d.aantalChunks} fragmenten` : kb;
}

// Inzichten komen na het verwerken; zolang het document zelf nog niet klaar is, niets tonen.
function inzichtenBadge(d: KbDocument): { tekst: string; kleur: string } | null {
  if (d.status !== 'gereed') return null;
  switch (d.inzichtenStatus) {
    case 'wachtrij':
      return { tekst: 'Inzichten in de wachtrij', kleur: 'neutral' };
    case 'verwerken':
      return {
        tekst: d.inzichtenSectiesTotaal
          ? `Inzichten ${d.inzichtenSectiesKlaar}/${d.inzichtenSectiesTotaal}`
          : 'Inzichten worden gemaakt',
        kleur: 'accent',
      };
    case 'fout':
      return { tekst: 'Inzichten mislukt', kleur: 'critical' };
    default:
      return { tekst: d.aantalInzichten === 1 ? '1 inzicht' : `${d.aantalInzichten} inzichten`, kleur: 'success' };
  }
}

// Het lampje blijft klikbaar, ook als er nog niets is: het paneel laat dan de voortgang zien.
function inzichtenNogNiet(d: KbDocument) {
  return bezigeStatus(d.inzichtenStatus) && d.aantalInzichten === 0;
}

const voortgang = computed(() => {
  const klaar = documenten.value.filter((d) => d.status === 'gereed');
  const onderweg = klaar.filter((d) => bezigeStatus(d.inzichtenStatus));
  return { onderweg: onderweg.length, klaar: klaar.length - onderweg.length, totaal: klaar.length };
});

function inzichtenBijgewerkt(doc: KbDocument) {
  const i = documenten.value.findIndex((d) => d.id === doc.id);
  if (i >= 0) documenten.value[i] = doc;
  laad();
}

onMounted(laad);
onUnmounted(() => window.clearTimeout(timer));
</script>

<template>
  <nldd-container gap="24">
    <nldd-box>
      <nldd-container padding="16" gap="16">
        <nldd-form-field
          label="Documenten toevoegen"
          supporting-label="PDF, Word, PowerPoint, Excel, ODT, HTML, Markdown, tekst of CSV"
        >
          <nldd-file-field :key="veldKey" multiple :accept="ACCEPT" @change="kies"></nldd-file-field>
        </nldd-form-field>
        <nldd-container layout="row">
          <nldd-button appearance="primary" start-icon="upload" text="Uploaden" :loading="bezig" @click="upload"></nldd-button>
        </nldd-container>
      </nldd-container>
    </nldd-box>

    <nldd-banner
      v-if="melding"
      :variant="melding.variant"
      :text="melding.text"
      :supporting-text="melding.supporting"
      dismissible
      @dismiss="melding = null"
    ></nldd-banner>

    <nldd-banner
      v-if="voortgang.onderweg"
      variant="accent"
      icon="lightbulb"
      :text="`Inzichten worden gemaakt: ${voortgang.klaar} van ${voortgang.totaal} documenten klaar`"
      supporting-text="Het taalmodel leest elk document helemaal, sectie voor sectie, kleine documenten eerst. Bij grote documenten kan dat lang duren, zeker met een lokaal model. Vragen stellen kan intussen gewoon."
    ></nldd-banner>

    <nldd-list appearance="box-base" accessible-label="Documenten">
      <nldd-list-item v-for="d in documenten" :key="d.id">
        <nldd-icon-cell :icon="icoon(d.bestandsnaam)" :color="d.status === 'fout' ? 'critical' : 'content'"></nldd-icon-cell>
        <nldd-spacer-cell size="8"></nldd-spacer-cell>
        <nldd-text-cell :text="d.bestandsnaam" :supporting-text="omschrijving(d)"></nldd-text-cell>
        <nldd-spacer-cell size="8"></nldd-spacer-cell>
        <nldd-cell>
          <nldd-badge size="sm" :color="STATUS[d.status].kleur" :text="STATUS[d.status].tekst"></nldd-badge>
        </nldd-cell>
        <template v-if="inzichtenBadge(d)">
          <nldd-spacer-cell size="8"></nldd-spacer-cell>
          <nldd-cell>
            <nldd-badge size="sm" :color="inzichtenBadge(d)!.kleur" :text="inzichtenBadge(d)!.tekst"></nldd-badge>
          </nldd-cell>
          <nldd-spacer-cell size="8"></nldd-spacer-cell>
          <nldd-cell>
            <nldd-icon-button
              icon="lightbulb"
              appearance="neutral-transparent"
              size="sm"
              :text="inzichtenNogNiet(d) ? `Voortgang van de inzichten uit ${d.bestandsnaam}` : `Inzichten uit ${d.bestandsnaam} bekijken`"
              @click="inzichtenVan = d.id"
            ></nldd-icon-button>
          </nldd-cell>
        </template>
        <nldd-spacer-cell size="8"></nldd-spacer-cell>
        <nldd-cell>
          <nldd-icon-button
            icon="trash"
            appearance="neutral-transparent"
            size="sm"
            :text="`${d.bestandsnaam} verwijderen`"
            @click="teVerwijderen = d"
          ></nldd-icon-button>
        </nldd-cell>
      </nldd-list-item>
      <nldd-inline-dialog
        slot="empty"
        icon="documents"
        text="Nog geen documenten"
        supporting-text="Voeg hierboven documenten toe. Ze worden automatisch gelezen en doorzoekbaar gemaakt, en daarna haalt de assistent er de inzichten uit."
      ></nldd-inline-dialog>
    </nldd-list>
  </nldd-container>

  <Teleport to="body">
    <InzichtenSheet
      :open="!!inzichtenDoc"
      :kennisbank="kennisbank"
      :document="inzichtenDoc"
      @close="inzichtenVan = null"
      @gewijzigd="inzichtenBijgewerkt"
    />
    <BevestigDialog
      :open="!!teVerwijderen"
      :text="`${teVerwijderen?.bestandsnaam ?? 'Document'} verwijderen?`"
      supporting-text="Het document en alle fragmenten ervan worden uit de kennisbank verwijderd. Antwoorden kunnen er daarna niet meer naar verwijzen."
      actie="Verwijder"
      @close="teVerwijderen = null"
      @bevestig="verwijder"
    />
  </Teleport>
</template>
