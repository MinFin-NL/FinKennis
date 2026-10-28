import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vite';

const backendPort = process.env.BACKEND_PORT ?? '8400';

export default defineConfig({
  plugins: [
    vue({
      template: {
        compilerOptions: {
          // nldd-* zijn web components, geen Vue-componenten.
          isCustomElement: (tag) => tag.startsWith('nldd-'),
        },
      },
    }),
  ],
  server: {
    port: 5190,
    proxy: {
      '/api': `http://localhost:${backendPort}`,
    },
  },
});
