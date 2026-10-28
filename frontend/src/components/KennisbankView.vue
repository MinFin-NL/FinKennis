<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { api, type Kennisbank } from '../api';
import BevestigDialog from './BevestigDialog.vue';
import ChatInvoer from './ChatInvoer.vue';
import ChatTab from './ChatTab.vue';
import DocumentenTab from './DocumentenTab.vue';
import KennisbankSheet from './KennisbankSheet.vue';

const props = defineProps<{ kennisbank: Kennisbank }>();
const emit = defineEmits<{ bijgewerkt: [kb: Kennisbank]; verwijderd: [id: string]; terug: [] }>();

const tab = ref<'chat' | 'documenten'>(props.kennisbank.aantalDocumenten ? 'chat' : 'documenten');
const sheetOpen = ref(false);
const verwijderOpen = ref(false);
const chat = ref<InstanceType<typeof ChatTab> | null>(null);

// nldd-page 0.13.0 zet in root-scrollmodus (smal scherm, één kolom) de sticky footer zijn eigen
// hoogte boven de onderrand. Daarom alleen een sticky invoerveld als de pagina zelf scrolt;
// op smal staat het veld gewoon onder het gesprek. De pagina meldt de modus in data-scroll.
const pagina = ref<HTMLElement | null>(null);
const rootScroll = ref(false);
let observer: MutationObserver | undefined;
onMounted(() => {
  const el = pagina.value;
  if (!el) return;
  const lees = () => (rootScroll.value = el.dataset.scroll === 'root');
  observer = new MutationObserver(lees);
  observer.observe(el, { attributes: true, attributeFilter: ['data-scroll'] });
  lees();
});
onUnmounted(() => observer?.disconnect());

function kiesTab(e: Event) {
  const item = (e as CustomEvent).detail?.item as HTMLElement | undefined;
  tab.value = item?.dataset.tab === 'documenten' ? 'documenten' : 'chat';
}

async function verwijder() {
  await api.verwijderKennisbank(props.kennisbank.id);
  emit('verwijderd', props.kennisbank.id);
}

function documentenGewijzigd(aantal: number) {
  if (aantal !== props.kennisbank.aantalDocumenten) {
    emit('bijgewerkt', { ...props.kennisbank, aantalDocumenten: aantal });
  }
}
</script>

<template>
  <nldd-page
    ref="pagina"
    landmarks="page"
    :accessible-label="kennisbank.naam"
    sticky-header
    :stickyFooter="tab === 'chat' && !rootScroll"
  >
    <nldd-top-title-bar
      slot="header"
      :text="kennisbank.naam"
      back-text="Kennisbanken"
      collapse-anchor="kennisbank-titel"
      @back="emit('terug')"
    >
      <nldd-icon-button slot="toolbar" icon="pencil" text="Kennisbank bewerken" @click="sheetOpen = true"></nldd-icon-button>
      <nldd-icon-button
        slot="toolbar"
        icon="trash"
        text="Kennisbank verwijderen"
        @click="verwijderOpen = true"
      ></nldd-icon-button>
    </nldd-top-title-bar>

    <nldd-simple-section grow>
      <nldd-container slot="header" gap="16">
        <nldd-title
          id="kennisbank-titel"
          size="2"
          heading-level="1"
          :text="kennisbank.naam"
          :supporting-text="kennisbank.omschrijving || undefined"
        ></nldd-title>
        <nldd-tab-bar accessible-label="Onderdelen" @select="kiesTab">
          <nldd-tab-bar-item data-tab="chat" icon="message-rectangle-text" text="Chat" :current="tab === 'chat'"></nldd-tab-bar-item>
          <nldd-tab-bar-item
            data-tab="documenten"
            icon="documents"
            text="Documenten"
            :current="tab === 'documenten'"
          ></nldd-tab-bar-item>
        </nldd-tab-bar>
      </nldd-container>

      <ChatTab v-if="tab === 'chat'" ref="chat" :kennisbank="kennisbank" @naar-documenten="tab = 'documenten'" />
      <DocumentenTab v-else :kennisbank="kennisbank" @gewijzigd="documentenGewijzigd" />
    </nldd-simple-section>

    <ChatInvoer
      v-if="tab === 'chat'"
      slot="footer"
      :bezig="chat?.bezig ?? false"
      :vervolg="!!chat?.actief"
      @verstuur="chat?.verstuur($event)"
      @stop="chat?.stop()"
    />
  </nldd-page>

  <Teleport to="body">
    <KennisbankSheet
      :open="sheetOpen"
      :kennisbank="kennisbank"
      @close="sheetOpen = false"
      @opgeslagen="emit('bijgewerkt', { ...$event, aantalDocumenten: kennisbank.aantalDocumenten })"
    />
    <BevestigDialog
      :open="verwijderOpen"
      :text="`${kennisbank.naam} verwijderen?`"
      supporting-text="De kennisbank, alle documenten en alle gesprekken worden verwijderd. Dit kun je niet ongedaan maken."
      actie="Verwijder"
      @close="verwijderOpen = false"
      @bevestig="verwijder"
    />
  </Teleport>
</template>
