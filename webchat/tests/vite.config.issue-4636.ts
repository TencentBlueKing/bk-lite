import path from 'node:path';
import { fileURLToPath } from 'node:url';

const testsDirectory = path.dirname(fileURLToPath(import.meta.url));
const webchatDirectory = path.resolve(testsDirectory, '..');

export default {
  resolve: {
    alias: {
      '@ant-design/x': path.resolve(testsDirectory, 'stubs/ant-design-x.tsx'),
      '@webchat/core': path.resolve(webchatDirectory, 'packages/webchat-core/src/index.ts'),
    },
  },
  build: {
    emptyOutDir: true,
    outDir: path.resolve(webchatDirectory, '.test-dist/issue-4636'),
    rollupOptions: {
      external: ['react', 'react-test-renderer'],
      output: {
        entryFileNames: 'chat-state-callback.issue-4636.test.mjs',
        format: 'es',
      },
    },
    ssr: path.resolve(testsDirectory, 'chat-state-callback.issue-4636.test.ts'),
  },
  ssr: {
    noExternal: true,
  },
};
