import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
  },
  build: {
    outDir: 'dist/browser',
    lib: {
      entry: path.resolve(__dirname, 'src/browser-entry.ts'),
      name: 'WebChat',
      formats: ['umd'],
      fileName: () => 'webchat.js',
    },
    rollupOptions: {
      // 不 external 任何依赖，全部打包进去
      external: [],
      output: {
        globals: {},
        inlineDynamicImports: true,
      },
    },
    sourcemap: true,
    minify: 'terser',
    cssCodeSplit: false,
  },
});
