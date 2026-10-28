<script setup lang="ts">
defineProps<{ open: boolean; text: string; supportingText: string; actie: string }>();
const emit = defineEmits<{ close: []; bevestig: [] }>();
</script>

<template>
  <nldd-modal-dialog
    variant="alert"
    :open="open"
    :text="text"
    :supporting-text="supportingText"
    @close="emit('close')"
  >
    <!-- De veilige weg terug komt eerst, als primaire knop. -->
    <nldd-button slot="actions" appearance="primary" text="Annuleer" @click="emit('close')"></nldd-button>
    <nldd-button
      slot="actions"
      appearance="destructive"
      :text="actie"
      @click="emit('bevestig'); emit('close')"
    ></nldd-button>
  </nldd-modal-dialog>
</template>
