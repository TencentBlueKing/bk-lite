import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@webchat/core': path.resolve(__dirname, './packages/webchat-core/src'),
      '@webchat/ui': path.resolve(__dirname, './packages/webchat-ui/src'),
    },
  },
  build: {
    lib: {
      entry: path.resolve(__dirname, 'packages/webchat-ui/src/index.ts'),
      name: 'WebChat',
      formats: ['umd', 'es'],
      fileName: (format) => {
        if (format === 'umd') return 'index.umd.js';
        if (format === 'es') return 'index.es.js';
        return 'index.js';
      },
    },
    rollupOptions: {
      external: ['react', 'react-dom'],
      output: {
        globals: {
          react: 'React',
          'react-dom': 'ReactDOM',
        },
      },
    },
    outDir: path.resolve(__dirname, 'dist'),
    sourcemap: true,
  },
});
