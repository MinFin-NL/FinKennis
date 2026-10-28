<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { api, type Kennisbank } from './api';
import { authEnabled, gebruikersnaam, logout } from './auth';
import KennisbankSheet from './components/KennisbankSheet.vue';
import KennisbankView from './components/KennisbankView.vue';

const kennisbanken = ref<Kennisbank[]>([]);
const geladen = ref(false);
const fout = ref<string | null>(null);
const sheetOpen = ref(false);

// Eenvoudige hash-router: #/kennisbanken/<id>. Zo werken links, de terugknop en herladen.
const huidigId = ref<string | null>(null);
function leesHash() {
  const m = window.location.hash.match(/^#\/kennisbanken\/([0-9a-f-]+)/);
  huidigId.value = m ? m[1] : null;
}
const huidig = computed(() => kennisbanken.value.find((k) => k.id === huidigId.value) ?? null);

async function laad() {
  try {
    kennisbanken.value = await api.kennisbanken();
    fout.value = null;
  } catch (e) {
    fout.value = (e as Error).message;
  } finally {
    geladen.value = true;
  }
}

function aangemaakt(kb: Kennisbank) {
  kennisbanken.value.unshift(kb);
  window.location.hash = `#/kennisbanken/${kb.id}`;
}

function bijgewerkt(kb: Kennisbank) {
  const i = kennisbanken.value.findIndex((k) => k.id === kb.id);
  if (i >= 0) kennisbanken.value[i] = kb;
}

function naarLijst() {
  window.location.hash = '';
}

function verwijderd(id: string) {
  kennisbanken.value = kennisbanken.value.filter((k) => k.id !== id);
  naarLijst();
}

onMounted(() => {
  leesHash();
  window.addEventListener('hashchange', leesHash);
  laad();
});
onUnmounted(() => window.removeEventListener('hashchange', leesHash));
</script>

<template>
  <nldd-skip-link text="Direct naar de inhoud"></nldd-skip-link>
  <nldd-shell>
    <nldd-bar-split-view>
      <!-- Bètamelding, gelijk aan de invulhulp: de NLDD-statusbalk hoort helemaal bovenaan en
           draagt één actie, dus de hele balk is de mailto-link. -->
      <nldd-split-view-pane slot="status">
        <nldd-status-bar
          variant="warning"
          text="Dit is een bètaversie van dit hulpmiddel. Vragen of feedback? innovatiemanagementfinancien@minfin.nl"
          href="mailto:innovatiemanagementfinancien@minfin.nl"
        ></nldd-status-bar>
      </nldd-split-view-pane>
      <nldd-split-view-pane slot="main">
        <nldd-navigation-split-view primary-sidebar-accessible-label="Kennisbanken">
          <nldd-split-view-pane slot="primary-sidebar" has-content background="tinted">
            <nldd-page accessible-label="Kennisbanken">
              <nldd-top-title-bar slot="header" text="FinKennis" heading-level="2">
                <nldd-icon-button
                  slot="toolbar"
                  icon="plus"
                  text="Nieuwe kennisbank"
                  @click="sheetOpen = true"
                ></nldd-icon-button>
                <nldd-icon-button
                  v-if="authEnabled"
                  slot="toolbar"
                  icon="logout"
                  :text="`Uitloggen (${gebruikersnaam() ?? 'gebruiker'})`"
                  @click="logout()"
                ></nldd-icon-button>
              </nldd-top-title-bar>

              <nldd-simple-section>
                <nldd-banner v-if="fout" variant="critical" text="Kennisbanken laden mislukt" :supporting-text="fout">
                  <nldd-button slot="actions" text="Opnieuw proberen" @click="laad"></nldd-button>
                </nldd-banner>
                <nldd-activity-indicator v-else-if="!geladen"></nldd-activity-indicator>
                <nldd-list v-else type="navigation" accessible-label="Kennisbanken">
                  <nldd-list-item
                    v-for="kb in kennisbanken"
                    :key="kb.id"
                    :href="`#/kennisbanken/${kb.id}`"
                    :current="kb.id === huidigId"
                  >
                    <nldd-icon-cell icon="books"></nldd-icon-cell>
                    <nldd-spacer-cell size="8"></nldd-spacer-cell>
                    <nldd-text-cell
                      :text="kb.naam"
                      :supporting-text="kb.aantalDocumenten === 1 ? '1 document' : `${kb.aantalDocumenten} documenten`"
                    ></nldd-text-cell>
                  </nldd-list-item>
                  <nldd-inline-dialog
                    slot="empty"
                    icon="books"
                    text="Nog geen kennisbanken"
                    supporting-text="Maak een kennisbank en voeg documenten toe om er vragen over te stellen."
                  >
                    <nldd-button
                      slot="actions"
                      appearance="primary"
                      start-icon="plus"
                      text="Nieuwe kennisbank"
                      @click="sheetOpen = true"
                    ></nldd-button>
                  </nldd-inline-dialog>
                </nldd-list>
              </nldd-simple-section>
            </nldd-page>
          </nldd-split-view-pane>

          <!-- Als property binden (camelCase): een kebab-case binding zet het attribuut ook bij false. -->
          <nldd-split-view-pane slot="main" :hasContent="!!huidig">
            <KennisbankView
              v-if="huidig"
              :key="huidig.id"
              :kennisbank="huidig"
              @bijgewerkt="bijgewerkt"
              @verwijderd="verwijderd"
              @terug="naarLijst"
            />
            <nldd-page v-else landmarks="page" accessible-label="Inhoud">
              <nldd-simple-section grow vertical-alignment="center">
                <nldd-inline-dialog
                  icon="message-rectangle-text"
                  text="Kies een kennisbank"
                  supporting-text="Kies links een kennisbank om documenten te beheren of er vragen over te stellen."
                ></nldd-inline-dialog>
              </nldd-simple-section>
            </nldd-page>
          </nldd-split-view-pane>
        </nldd-navigation-split-view>
      </nldd-split-view-pane>
    </nldd-bar-split-view>
  </nldd-shell>

  <Teleport to="body">
    <KennisbankSheet :open="sheetOpen" @close="sheetOpen = false" @opgeslagen="aangemaakt" />
  </Teleport>
</template>
