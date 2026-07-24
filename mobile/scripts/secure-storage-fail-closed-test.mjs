import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const projectRoot = new URL('../', import.meta.url);

function findDeclaration(sourceFile, name) {
  const declaration = sourceFile.statements.find((node) => {
    if (ts.isFunctionDeclaration(node)) {
      return node.name?.text === name;
    }
    if (ts.isVariableStatement(node)) {
      return node.declarationList.declarations.some(
        (item) => ts.isIdentifier(item.name) && item.name.text === name,
      );
    }
    return false;
  });

  assert.ok(declaration, `secureStorage.ts must declare ${name}`);
  return declaration.getText(sourceFile);
}

async function loadSecureStorage() {
  const source = await readFile(new URL('src/utils/secureStorage.ts', projectRoot), 'utf8');
  const sourceFile = ts.createSourceFile(
    'secureStorage.ts',
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  const declarations = [
    'STORAGE_KEYS',
    'STORE_FILE',
    'memoryCache',
    'storeInstance',
    'isInitialized',
    'isTauriEnvironment',
    'clearLegacyAuthStorage',
    'getStore',
    'initSecureStorage',
    'secureSet',
    'secureGetSync',
    'saveToken',
    'getTokenSync',
  ].map((name) => findDeclaration(sourceFile, name));
  const moduleSource = `${declarations.join('\n')}\nexport { getStore, initSecureStorage, saveToken, getTokenSync };`.replace(
    "import('@tauri-apps/plugin-store')",
    'globalThis.__loadStoreModule()',
  );
  const output = ts.transpileModule(moduleSource, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(output).toString('base64')}#${Date.now()}-${Math.random()}`;

  return await import(moduleUrl);
}

function installWindow(initialValues = {}, tauri = false) {
  const values = new Map(Object.entries(initialValues));
  const setCalls = [];
  const localStorage = {
    getItem: (key) => values.get(key) ?? null,
    removeItem: (key) => values.delete(key),
    setItem: (key, value) => {
      setCalls.push([key, value]);
      values.set(key, value);
    },
  };
  globalThis.window = tauri ? { __TAURI_INTERNALS__: {}, localStorage } : { localStorage };
  globalThis.localStorage = localStorage;
  return { setCalls, values };
}

test.afterEach(() => {
  delete globalThis.__loadStoreModule;
  delete globalThis.localStorage;
  delete globalThis.window;
});

test('H5 keeps the explicit localStorage fallback without loading the Tauri plugin', async () => {
  const { values } = installWindow({ auth_token: 'h5-token' });
  let loaderCalls = 0;
  globalThis.__loadStoreModule = async () => {
    loaderCalls += 1;
    throw new Error('must not load');
  };
  const { getStore } = await loadSecureStorage();

  assert.equal(await getStore(), null);
  assert.equal(loaderCalls, 0);
  assert.equal(values.get('auth_token'), 'h5-token');
});

test('Tauri Store load failure clears legacy auth copies and never becomes a fallback signal', async () => {
  const { values } = installWindow(
    {
      auth_token: 'legacy-token',
      refresh_token: 'legacy-refresh-token',
      user_info: '{"username":"legacy"}',
      locale: 'zh-CN',
    },
    true,
  );
  globalThis.__loadStoreModule = async () => {
    throw new Error('store unavailable');
  };
  const { getStore } = await loadSecureStorage();

  const originalConsoleError = console.error;
  console.error = () => {};
  try {
    await assert.rejects(getStore(), /store unavailable/);
  } finally {
    console.error = originalConsoleError;
  }
  assert.equal(values.has('auth_token'), false);
  assert.equal(values.has('refresh_token'), false);
  assert.equal(values.has('user_info'), false);
  assert.equal(values.get('locale'), 'zh-CN');
});

test('Tauri Store success keeps using the canonical store after legacy cleanup', async () => {
  const { values } = installWindow({ auth_token: 'legacy-token' }, true);
  const store = { get() {}, set() {} };
  globalThis.__loadStoreModule = async () => ({
    load: async () => store,
  });
  const { getStore } = await loadSecureStorage();

  assert.equal(await getStore(), store);
  assert.equal(values.has('auth_token'), false);
});

test('saveToken rejects and leaves no cached token when the Tauri Store cannot load', async () => {
  const { setCalls, values } = installWindow({ auth_token: 'legacy-token' }, true);
  globalThis.__loadStoreModule = async () => {
    throw new Error('store unavailable');
  };
  const { getTokenSync, saveToken } = await loadSecureStorage();
  const originalConsoleError = console.error;
  console.error = () => {};

  try {
    await assert.rejects(saveToken('new-token'), /store unavailable/);
  } finally {
    console.error = originalConsoleError;
  }

  assert.deepEqual(setCalls, []);
  assert.equal(values.has('auth_token'), false);
  assert.equal(getTokenSync(), null);
});

test('saveToken rejects and updates the cache only after the Tauri Store is saved', async () => {
  installWindow({}, true);
  const store = {
    set: async () => {},
    save: async () => {
      throw new Error('save failed');
    },
  };
  globalThis.__loadStoreModule = async () => ({
    load: async () => store,
  });
  const { getTokenSync, saveToken } = await loadSecureStorage();
  const originalConsoleError = console.error;
  console.error = () => {};

  try {
    await assert.rejects(saveToken('new-token'), /save failed/);
  } finally {
    console.error = originalConsoleError;
  }

  assert.equal(getTokenSync(), null);
});

test('initSecureStorage rejects Tauri read failures without caching partial auth state', async () => {
  installWindow({}, true);
  const store = {
    get: async (key) => {
      if (key === 'auth_token') {
        return 'persisted-token';
      }
      throw new Error('read failed');
    },
  };
  globalThis.__loadStoreModule = async () => ({
    load: async () => store,
  });
  const { getTokenSync, initSecureStorage } = await loadSecureStorage();
  const originalConsoleError = console.error;
  console.error = () => {};

  try {
    await assert.rejects(initSecureStorage(), /read failed/);
  } finally {
    console.error = originalConsoleError;
  }

  assert.equal(getTokenSync(), null);
});
