<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api, type Gebruiker } from '../api';
import BevestigDialog from './BevestigDialog.vue';
import GebruikerSheet from './GebruikerSheet.vue';

const emit = defineEmits<{ terug: [] }>();

const gebruikers = ref<Gebruiker[]>([]);
const geladen = ref(false);
const bezig = ref(false);
const fout = ref<string | null>(null);
const melding = ref<string | null>(null);
const wachtwoord = ref<{ voor: string; waarde: string } | null>(null);
const gekopieerd = ref(false);
const sheetOpen = ref(false);
const teVerwijderen = ref<Gebruiker | null>(null);

function naam(g: Gebruiker): string {
  return [g.voornaam, g.achternaam].filter(Boolean).join(' ') || g.email || g.gebruikersnaam || 'Gebruiker';
}

async function laad() {
  try {
    gebruikers.value = await api.gebruikers();
    fout.value = null;
  } catch (e) {
    fout.value = (e as Error).message;
  } finally {
    geladen.value = true;
  }
}

onMounted(laad);

/** Voert een beheeractie uit en laadt daarna de lijst opnieuw. */
async function voerUit(actie: () => Promise<void>) {
  bezig.value = true;
  fout.value = null;
  melding.value = null;
  try {
    await actie();
    await laad();
  } catch (e) {
    fout.value = (e as Error).message;
  } finally {
    bezig.value = false;
  }
}

function toonWachtwoord(voor: string, waarde: string) {
  wachtwoord.value = { voor, waarde };
  gekopieerd.value = false;
}

function aangemaakt(email: string, tijdelijk: string) {
  toonWachtwoord(email, tijdelijk);
  laad();
}

function resetWachtwoord(g: Gebruiker) {
  voerUit(async () => {
    const res = await api.resetWachtwoord(g.id);
    toonWachtwoord(g.email ?? naam(g), res.tijdelijkWachtwoord);
  });
}

function wisselBeheerder(g: Gebruiker) {
  voerUit(async () => {
    await api.wijzigGebruiker(g.id, { beheerder: !g.beheerder });
    // De rol zit in het access token; dat wordt binnen vijf minuten vernieuwd.
    melding.value = g.beheerder
      ? `${naam(g)} is geen beheerder meer. Dat geldt binnen vijf minuten.`
      : `${naam(g)} is nu beheerder. Dat geldt binnen vijf minuten.`;
  });
}

function wisselActief(g: Gebruiker) {
  voerUit(async () => {
    await api.wijzigGebruiker(g.id, { actief: !g.actief });
    melding.value = g.actief ? `${naam(g)} is gedeactiveerd.` : `${naam(g)} is weer actief.`;
  });
}

function verwijder() {
  const g = teVerwijderen.value;
  if (!g) return;
  voerUit(async () => {
    await api.verwijderGebruiker(g.id);
    melding.value = `${naam(g)} is verwijderd.`;
  });
}

function verwijderTekst(g: Gebruiker | null): string {
  if (!g) return '';
  const kb =
    g.aantalKennisbanken === 0
      ? 'Deze gebruiker heeft geen kennisbanken.'
      : g.aantalKennisbanken === 1
        ? 'Ook de kennisbank van deze gebruiker gaat weg, met alle documenten en gesprekken.'
        : `Ook de ${g.aantalKennisbanken} kennisbanken van deze gebruiker gaan weg, met alle documenten en gesprekken.`;
  return `${naam(g)} verliest direct de toegang tot FinKennis. ${kb} Dit kun je niet ongedaan maken.`;
}

async function kopieer() {
  if (!wachtwoord.value) return;
  await navigator.clipboard.writeText(wachtwoord.value.waarde);
  gekopieerd.value = true;
}
</script>

<template>
  <nldd-page landmarks="page" accessible-label="Gebruikersbeheer" sticky-header>
    <nldd-top-title-bar
      slot="header"
      text="Gebruikersbeheer"
      back-text="Kennisbanken"
      collapse-anchor="gebruikersbeheer-titel"
      @back="emit('terug')"
    >
      <nldd-icon-button
        slot="toolbar"
        icon="person-badge-plus"
        text="Nieuwe gebruiker"
        @click="sheetOpen = true"
      ></nldd-icon-button>
    </nldd-top-title-bar>

    <nldd-simple-section>
      <nldd-container slot="header" gap="8">
        <nldd-title id="gebruikersbeheer-titel" size="2" heading-level="1" text="Gebruikersbeheer"></nldd-title>
        <nldd-text color="secondary">
          Gebruikers staan in Keycloak en loggen in met SSO. Iedere gebruiker heeft eigen kennisbanken
          en gesprekken. Een beheerder mag daarnaast gebruikers beheren. Een nieuwe gebruiker krijgt
          een tijdelijk wachtwoord en kiest bij de eerste keer inloggen een eigen wachtwoord.
        </nldd-text>
      </nldd-container>

      <nldd-container gap="16">
        <nldd-banner v-if="fout" variant="critical" text="Dat lukte niet" :supporting-text="fout"></nldd-banner>
        <nldd-banner v-if="melding" variant="success" :text="melding"></nldd-banner>
        <nldd-banner
          v-if="wachtwoord"
          variant="warning"
          :text="`Tijdelijk wachtwoord voor ${wachtwoord.voor}: ${wachtwoord.waarde}`"
          supporting-text="Geef dit één keer door; het wordt niet nog eens getoond. Bij de eerste keer inloggen kiest de gebruiker een eigen wachtwoord."
        >
          <nldd-button
            slot="actions"
            :text="gekopieerd ? 'Gekopieerd' : 'Kopieer'"
            start-icon="square-on-square"
            @click="kopieer"
          ></nldd-button>
          <nldd-button slot="actions" text="Sluit" @click="wachtwoord = null"></nldd-button>
        </nldd-banner>

        <nldd-activity-indicator v-if="!geladen"></nldd-activity-indicator>
        <div v-else class="tabel">
          <nldd-table
            columns="minmax(160px, 1.2fr) minmax(200px, 1.4fr) 120px 120px 130px 64px"
            accessible-label="Gebruikers"
          >
            <nldd-table-row slot="header">
              <nldd-text-cell size="sm" text="Naam"></nldd-text-cell>
              <nldd-text-cell size="sm" text="E-mail"></nldd-text-cell>
              <nldd-text-cell size="sm" text="Rol"></nldd-text-cell>
              <nldd-text-cell size="sm" text="Kennisbanken"></nldd-text-cell>
              <nldd-text-cell size="sm" text="Status"></nldd-text-cell>
              <nldd-text-cell size="sm" text="Acties"></nldd-text-cell>
            </nldd-table-row>
            <nldd-table-row v-for="g in gebruikers" :key="g.id" :class="{ inactief: !g.actief }">
              <nldd-text-cell :text="g.zelf ? `${naam(g)} (jij)` : naam(g)"></nldd-text-cell>
              <nldd-text-cell :text="g.email ?? g.gebruikersnaam ?? ''"></nldd-text-cell>
              <nldd-cell>
                <nldd-tag v-if="g.beheerder" size="sm" color="accent" text="Beheerder"></nldd-tag>
                <nldd-tag v-else size="sm" text="Gebruiker"></nldd-tag>
              </nldd-cell>
              <nldd-text-cell :text="String(g.aantalKennisbanken)"></nldd-text-cell>
              <nldd-cell>
                <nldd-tag
                  size="sm"
                  :color="g.actief ? 'success' : 'neutral'"
                  :text="g.actief ? 'Actief' : 'Gedeactiveerd'"
                ></nldd-tag>
              </nldd-cell>
              <nldd-cell>
                <nldd-icon-button icon="ellipsis" :text="`Acties voor ${naam(g)}`" :disabled="bezig" expandable>
                  <nldd-menu slot="popup">
                    <nldd-menu-item icon="key" text="Wachtwoord resetten" @select="resetWachtwoord(g)"></nldd-menu-item>
                    <nldd-menu-item
                      :icon="g.beheerder ? 'person-badge-minus' : 'person-badge-gear'"
                      :text="g.beheerder ? 'Beheerdersrol afnemen' : 'Beheerder maken'"
                      :disabled="g.zelf"
                      @select="wisselBeheerder(g)"
                    ></nldd-menu-item>
                    <nldd-menu-item
                      :icon="g.actief ? 'slash-circle' : 'check-mark-circle'"
                      :text="g.actief ? 'Deactiveren' : 'Activeren'"
                      :disabled="g.zelf"
                      @select="wisselActief(g)"
                    ></nldd-menu-item>
                    <nldd-menu-divider></nldd-menu-divider>
                    <nldd-menu-item
                      icon="trash"
                      text="Verwijderen"
                      destructive
                      :disabled="g.zelf"
                      @select="teVerwijderen = g"
                    ></nldd-menu-item>
                  </nldd-menu>
                </nldd-icon-button>
              </nldd-cell>
            </nldd-table-row>
          </nldd-table>
        </div>
      </nldd-container>
    </nldd-simple-section>
  </nldd-page>

  <Teleport to="body">
    <GebruikerSheet :open="sheetOpen" @close="sheetOpen = false" @aangemaakt="aangemaakt" />
    <BevestigDialog
      :open="!!teVerwijderen"
      :text="`${teVerwijderen ? naam(teVerwijderen) : ''} verwijderen?`"
      :supporting-text="verwijderTekst(teVerwijderen)"
      actie="Verwijder gebruiker"
      @close="teVerwijderen = null"
      @bevestig="verwijder"
    />
  </Teleport>
</template>

<style scoped>
.tabel {
  overflow-x: auto;
}

.inactief {
  opacity: 0.55;
}
</style>
