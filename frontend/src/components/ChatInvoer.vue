<script setup lang="ts">
import { computed, ref } from 'vue';
import type { InzichtenStatus, Modus } from '../api';

const props = defineProps<{ bezig: boolean; vervolg: boolean; inzichten: InzichtenStatus | null }>();
const emit = defineEmits<{ verstuur: [vraag: string, modus: Modus]; stop: [] }>();

// Inzichten zijn vooraf uit de hele documenten gehaald; een vraag is dan optioneel.
const STANDAARD_INZICHTVRAAG = 'Wat zijn de belangrijkste inzichten uit de documenten?';
const modus = ref<Modus>('vraag');
// De knop Inzichten blijft altijd klikbaar: een uitgeschakelde knop zegt niet waarom hij niet
// werkt. Wie hem kiest terwijl er nog niets is, krijgt hieronder uitleg en de voortgang.
const secties = computed(() => {
  const s = props.inzichten;
  return s?.sectiesTotaal ? `${s.sectiesKlaar} van ${s.sectiesTotaal} secties gelezen` : null;
});

const nogGeenInzichten = computed(() =>
  modus.value === 'inzichten' && props.inzichten !== null && !props.inzichten.aantalInzichten
    ? {
        tekst: props.inzichten.documentenOnderweg
          ? 'De inzichten worden nog gemaakt'
          : 'Er zijn nog geen inzichten in deze kennisbank',
        uitleg: props.inzichten.documentenOnderweg
          ? `Het taalmodel leest de documenten helemaal${secties.value ? ` (${secties.value})` : ''}, kleine documenten eerst. Zodra het eerste klaar is, kun je hier terecht. Gewone vragen kun je intussen wel stellen via Vraag.`
          : props.inzichten.documentenMislukt
            ? 'Het maken van de inzichten is mislukt. Probeer het opnieuw via Documenten, met het lampje bij een document.'
            : 'Inzichten worden gemaakt zodra er documenten zijn verwerkt. Voeg eerst documenten toe.',
      }
    : null,
);

// Als er al inzichten zijn maar nog niet voor alle documenten.
const voortgangTekst = computed(() => {
  const s = props.inzichten;
  if (!s?.documentenOnderweg || !s.aantalInzichten || nogGeenInzichten.value) return null;
  const docs = s.documentenOnderweg === 1 ? '1 document' : `${s.documentenOnderweg} documenten`;
  return `Inzichten voor ${docs} worden nog gemaakt${secties.value ? ` (${secties.value})` : ''}; die tellen nog niet mee.`;
});

const label = computed(() =>
  modus.value === 'inzichten' ? 'Waar wil je inzichten over? (optioneel)' : 'Je vraag',
);

const vraag = ref('');
// Bij elke verzending een nieuwe sleutel, zodat het veld echt leeg begint.
const veldKey = ref(0);

function waarde(e: Event): string {
  return (e as CustomEvent).detail?.value ?? (e.target as HTMLTextAreaElement)?.value ?? '';
}

function verstuur() {
  const tekst = vraag.value.trim() || (modus.value === 'inzichten' ? STANDAARD_INZICHTVRAAG : '');
  if (!tekst) return;
  emit('verstuur', tekst, modus.value);
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
  <nldd-container class="chat-invoer" padding="16" gap="8">
    <nldd-container layout="row" gap="4" vertical-alignment="center">
      <nldd-segmented-control
        size="sm"
        width="fit-content"
        accessible-label="Soort vraag"
        :value="modus"
        @change="modus = ($event as CustomEvent).detail.value"
      >
        <nldd-segmented-control-item value="vraag" text="Vraag"></nldd-segmented-control-item>
        <nldd-segmented-control-item value="inzichten" text="Inzichten"></nldd-segmented-control-item>
      </nldd-segmented-control>
      <!-- Een popover op klik in plaats van een tooltip op hover: de uitleg is te lang voor een
           tooltip, en zo werkt hij ook met aanraken en het toetsenbord. -->
      <nldd-icon-button
        id="modus-uitleg-knop"
        icon="info-circle"
        appearance="neutral-transparent"
        size="sm"
        text="Wat is het verschil tussen Vraag en Inzichten?"
        popovertarget="modus-uitleg"
      ></nldd-icon-button>
      <nldd-popover id="modus-uitleg" anchor="modus-uitleg-knop" placement="top-start" width="400px" accessible-label="Vraag of Inzichten">
        <nldd-container padding="16" gap="12">
          <nldd-title size="5" heading-level="2" text="Twee manieren om te vragen"></nldd-title>
          <nldd-container gap="4">
            <nldd-text weight="bold">Vraag: feiten uit de tekst</nldd-text>
            <nldd-text size="sm">
              Voor een bedrag, een datum of wat er over een onderwerp staat. De assistent zoekt de
              passende stukken tekst op en antwoordt alleen met wat daar staat, met bronnen. Staat
              het er niet, dan zegt hij dat. Niet bedoeld voor samenvattingen of "wat valt op?".
            </nldd-text>
          </nldd-container>
          <nldd-container gap="4">
            <nldd-text weight="bold">Inzichten: wat valt op</nldd-text>
            <nldd-text size="sm">
              Voor risico's, afwijkingen, besluiten en opvallende cijfers. Elk document is vooraf
              helemaal gelezen, ook de bijlagen; de assistent kiest uit wat daaruit kwam. Je kunt
              het leeg laten, een onderwerp noemen of doorvragen. Per document zie je de inzichten
              ook bij Documenten, via het lampje.
            </nldd-text>
          </nldd-container>
        </nldd-container>
      </nldd-popover>
    </nldd-container>
    <nldd-banner
      v-if="nogGeenInzichten"
      variant="accent"
      icon="lightbulb"
      :text="nogGeenInzichten.tekst"
      :supporting-text="nogGeenInzichten.uitleg"
    ></nldd-banner>
    <nldd-container v-if="voortgangTekst" layout="row" gap="8" vertical-alignment="center">
      <nldd-activity-indicator size="16"></nldd-activity-indicator>
      <nldd-text size="sm" color="secondary">{{ voortgangTekst }}</nldd-text>
    </nldd-container>
    <nldd-form-field
      :label="vervolg && modus === 'vraag' ? 'Stel een vervolgvraag' : label"
      :supporting-label="
        modus === 'inzichten'
          ? 'Wat valt op in de documenten. Laat leeg voor de belangrijkste inzichten, of noem een onderwerp.'
          : 'Alleen feiten die in de documenten staan, met bronnen. Voor wat er opvalt: kies Inzichten.'
      "
    >
      <nldd-multi-line-text-field
        :key="veldKey"
        :value="vraag"
        rows="2"
        maxlength="4000"
        @input="vraag = waarde($event)"
        @keydown="toets"
      ></nldd-multi-line-text-field>
      <nldd-form-field-help-text>
        Enter verstuurt, Shift+Enter voor een nieuwe regel. Antwoorden worden gemaakt door AI en
        kunnen fouten bevatten. Controleer ze in de bronnen.
      </nldd-form-field-help-text>
    </nldd-form-field>
    <nldd-container layout="row" horizontal-alignment="right" gap="8">
      <nldd-button v-if="bezig" appearance="secondary" text="Stop" @click="emit('stop')"></nldd-button>
      <nldd-button appearance="primary" start-icon="paper-plane" text="Verstuur" :loading="bezig" @click="verstuur"></nldd-button>
    </nldd-container>
  </nldd-container>
</template>

<style scoped>
/* De sticky footer van nldd-page is maar 95% dekkend; daardoor schemert het antwoord erdoorheen. */
.chat-invoer {
  background-color: var(--context-parent-background-color, var(--semantics-surfaces-base-background-color));
}
</style>
