<script setup lang="ts">
import { ref, watch } from 'vue';
import { api, type Kennisbank } from '../api';

const props = defineProps<{ open: boolean; kennisbank?: Kennisbank }>();
const emit = defineEmits<{ close: []; opgeslagen: [kb: Kennisbank] }>();

const naam = ref('');
const omschrijving = ref('');
const naamOntbreekt = ref(false);
const bezig = ref(false);
const fout = ref<string | null>(null);

// Bij openen de velden vullen; de sheet blijft in de DOM, dus dit gebeurt niet vanzelf.
watch(
  () => props.open,
  (open) => {
    if (!open) return;
    naam.value = props.kennisbank?.naam ?? '';
    omschrijving.value = props.kennisbank?.omschrijving ?? '';
    naamOntbreekt.value = false;
    fout.value = null;
  },
);

function waarde(e: Event): string {
  return (e as CustomEvent).detail?.value ?? (e.target as HTMLInputElement)?.value ?? '';
}

async function bewaar() {
  naamOntbreekt.value = !naam.value.trim();
  if (naamOntbreekt.value) return;
  bezig.value = true;
  fout.value = null;
  try {
    const kb = props.kennisbank
      ? await api.wijzigKennisbank(props.kennisbank.id, naam.value.trim(), omschrijving.value)
      : await api.maakKennisbank(naam.value.trim(), omschrijving.value);
    emit('opgeslagen', kb);
    emit('close');
  } catch (e) {
    fout.value = (e as Error).message;
  } finally {
    bezig.value = false;
  }
}

const titel = () => (props.kennisbank ? 'Kennisbank bewerken' : 'Nieuwe kennisbank');
</script>

<template>
  <nldd-sheet placement="right" width="480px" :open="open" @close="emit('close')">
    <nldd-page>
      <nldd-top-title-bar
        slot="header"
        :text="titel()"
        dismiss-text="Annuleer"
        collapse-anchor="kennisbank-sheet-titel"
        @dismiss="emit('close')"
      ></nldd-top-title-bar>
      <nldd-simple-section>
        <nldd-title
          id="kennisbank-sheet-titel"
          slot="header"
          size="2"
          :text="titel()"
          heading-level="1"
        ></nldd-title>
        <nldd-form name="kennisbank" @submit.prevent>
          <nldd-banner v-if="fout" variant="critical" text="Bewaren mislukt" :supporting-text="fout"></nldd-banner>
          <nldd-form-field label="Naam">
            <nldd-text-field
              name="naam"
              :value="naam"
              :invalid="naamOntbreekt"
              maxlength="200"
              @input="naam = waarde($event)"
            ></nldd-text-field>
            <nldd-form-field-help-text v-if="naamOntbreekt">Vul een naam in.</nldd-form-field-help-text>
          </nldd-form-field>
          <nldd-form-field label="Omschrijving" optional>
            <nldd-multi-line-text-field
              name="omschrijving"
              :value="omschrijving"
              maxlength="2000"
              @input="omschrijving = waarde($event)"
            ></nldd-multi-line-text-field>
          </nldd-form-field>
          <nldd-form-actions>
            <nldd-button-group>
              <nldd-button appearance="primary" type="button" text="Bewaar" :loading="bezig" @click="bewaar"></nldd-button>
            </nldd-button-group>
          </nldd-form-actions>
        </nldd-form>
      </nldd-simple-section>
    </nldd-page>
  </nldd-sheet>
</template>
