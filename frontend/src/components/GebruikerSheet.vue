<script setup lang="ts">
import { ref, watch } from 'vue';
import { api } from '../api';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: []; aangemaakt: [email: string, tijdelijkWachtwoord: string] }>();

const voornaam = ref('');
const achternaam = ref('');
const email = ref('');
const beheerder = ref(false);
const ontbreekt = ref(false);
const bezig = ref(false);
const fout = ref<string | null>(null);

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    voornaam.value = achternaam.value = email.value = '';
    beheerder.value = false;
    ontbreekt.value = false;
    fout.value = null;
  },
);

function waarde(e: Event): string {
  return (e as CustomEvent).detail?.value ?? (e.target as HTMLInputElement)?.value ?? '';
}

function aangevinkt(e: Event): boolean {
  return (e as CustomEvent).detail?.checked ?? (e.target as HTMLInputElement)?.checked ?? false;
}

async function bewaar() {
  ontbreekt.value = !voornaam.value.trim() || !achternaam.value.trim() || !email.value.trim();
  if (ontbreekt.value) return;
  bezig.value = true;
  fout.value = null;
  try {
    const res = await api.maakGebruiker(
      voornaam.value.trim(),
      achternaam.value.trim(),
      email.value.trim(),
      beheerder.value,
    );
    emit('aangemaakt', email.value.trim().toLowerCase(), res.tijdelijkWachtwoord);
    emit('close');
  } catch (e) {
    fout.value = (e as Error).message;
  } finally {
    bezig.value = false;
  }
}
</script>

<template>
  <nldd-sheet placement="right" width="480px" :open="open" @close="emit('close')">
    <nldd-page>
      <nldd-top-title-bar
        slot="header"
        text="Nieuwe gebruiker"
        dismiss-text="Annuleer"
        collapse-anchor="gebruiker-sheet-titel"
        @dismiss="emit('close')"
      ></nldd-top-title-bar>
      <nldd-simple-section>
        <nldd-title
          id="gebruiker-sheet-titel"
          slot="header"
          size="2"
          text="Nieuwe gebruiker"
          heading-level="1"
        ></nldd-title>
        <nldd-form name="gebruiker" @submit.prevent>
          <nldd-banner v-if="fout" variant="critical" text="Aanmaken mislukt" :supporting-text="fout"></nldd-banner>
          <nldd-form-field label="Voornaam">
            <nldd-text-field
              name="voornaam"
              :value="voornaam"
              :invalid="ontbreekt && !voornaam.trim()"
              maxlength="100"
              @input="voornaam = waarde($event)"
            ></nldd-text-field>
          </nldd-form-field>
          <nldd-form-field label="Achternaam">
            <nldd-text-field
              name="achternaam"
              :value="achternaam"
              :invalid="ontbreekt && !achternaam.trim()"
              maxlength="100"
              @input="achternaam = waarde($event)"
            ></nldd-text-field>
          </nldd-form-field>
          <nldd-form-field label="E-mailadres">
            <nldd-text-field
              name="email"
              type="email"
              :value="email"
              :invalid="ontbreekt && !email.trim()"
              maxlength="254"
              @input="email = waarde($event)"
            ></nldd-text-field>
            <nldd-form-field-help-text>Dit wordt ook de gebruikersnaam.</nldd-form-field-help-text>
          </nldd-form-field>
          <nldd-checkbox-field
            label="Beheerder (mag gebruikers beheren)"
            :checked="beheerder"
            @change="beheerder = aangevinkt($event)"
          ></nldd-checkbox-field>
          <nldd-form-field-help-text v-if="ontbreekt">Vul alle velden in.</nldd-form-field-help-text>
          <nldd-form-actions>
            <nldd-button-group>
              <nldd-button
                appearance="primary"
                type="button"
                text="Gebruiker aanmaken"
                :loading="bezig"
                @click="bewaar"
              ></nldd-button>
            </nldd-button-group>
          </nldd-form-actions>
        </nldd-form>
      </nldd-simple-section>
    </nldd-page>
  </nldd-sheet>
</template>
