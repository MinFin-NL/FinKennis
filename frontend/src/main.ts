import '@nldd/design-system';
// Met RijksSans. Die is alleen voor de Rijksoverheid; wordt FinKennis buiten het Rijk
// hergebruikt, importeer dan '@nldd/design-system/styles/system-font'.
import '@nldd/design-system/styles';

import { createApp } from 'vue';
import App from './App.vue';
import { initAuth } from './auth';
import Landingspagina from './components/Landingspagina.vue';

initAuth().then((ingelogd) => {
  createApp(ingelogd ? App : Landingspagina).mount('#app');
});
