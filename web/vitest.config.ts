import path from 'node:path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      '@bk-lite/chat-content': path.resolve(__dirname, 'packages/chat-content/src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
});
