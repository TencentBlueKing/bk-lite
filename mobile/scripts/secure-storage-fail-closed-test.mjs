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
    'CREDENTIAL_KEYS',
    'memoryCache',
    'storeInstance',
    'isInitialized',
    'isTauriEnvironment',
    'isCredentialKey',
    'shouldUseNativeCredentialStore',
    'invokeSecureCredential',
    'credentialSet',
    'credentialGet',
    'credentialRemove',
    'clearLegacyAuthStorage',
    'getStore',
    'initSecureStorage',
    'secureSet',
    'secureGetSync',
    'secureRemove',
    'secureClear',
    'saveToken',
    'sanitizeUserInfoForStorage',
    'saveUserInfo',
    'getTokenSync',
    'clearAuthData',
  ].map((name) => findDeclaration(sourceFile, name));
  const moduleSource = `${declarations.join('\n')}\nexport { getStore, initSecureStorage, secureClear, saveToken, saveUserInfo, getTokenSync, clearAuthData };`
    .replaceAll("import('@tauri-apps/plugin-store')", 'globalThis.__loadStoreModule()')
    .replaceAll("import('@tauri-apps/api/core')", 'globalThis.__loadCoreModule()');
  const output = ts.transpileModule(moduleSource, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(output).toString('base64')}#${Date.now()}-${Math.random()}`;

  return await import(moduleUrl);
}

function installWindow(initialValues = {}, tauri = false, userAgent = 'Mozilla/5.0') {
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
  const navigator = { userAgent };
  globalThis.window = tauri
    ? { __TAURI_INTERNALS__: {}, localStorage, navigator }
    : { localStorage, navigator };
  globalThis.localStorage = localStorage;
  return { setCalls, values };
}

test.afterEach(() => {
  delete globalThis.__loadCoreModule;
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

test('saveToken writes Tauri tokens to native credentials without touching Tauri Store', async () => {
  const { setCalls } = installWindow({}, true);
  const credentialCalls = [];
  let storeLoaderCalls = 0;
  globalThis.__loadStoreModule = async () => {
    storeLoaderCalls += 1;
    throw new Error('must not load store for token');
  };
  globalThis.__loadCoreModule = async () => ({
    invoke: async (command, args) => {
      credentialCalls.push({ command, args });
      return null;
    },
  });
  const { getTokenSync, saveToken } = await loadSecureStorage();

  await saveToken('new-token');

  assert.deepEqual(credentialCalls, [
    {
      command: 'secure_credential_set',
      args: { key: 'auth_token', value: 'new-token' },
    },
  ]);
  assert.equal(storeLoaderCalls, 0);
  assert.deepEqual(setCalls, []);
  assert.equal(getTokenSync(), 'new-token');
});

test('saveToken rejects and leaves no cached token when native credential storage fails', async () => {
  const { setCalls } = installWindow({ auth_token: 'legacy-token' }, true);
  globalThis.__loadStoreModule = async () => {
    throw new Error('must not load store');
  };
  globalThis.__loadCoreModule = async () => ({
    invoke: async () => {
      throw new Error('credential unavailable');
    },
  });
  const { getTokenSync, saveToken } = await loadSecureStorage();
  const originalConsoleError = console.error;
  console.error = () => {};

  try {
    await assert.rejects(saveToken('new-token'), /credential unavailable/);
  } finally {
    console.error = originalConsoleError;
  }

  assert.deepEqual(setCalls, []);
  assert.equal(getTokenSync(), null);
});

test('Android Tauri stores tokens through native credentials without touching Tauri Store', async () => {
  installWindow({}, true, 'Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36');
  const credentialCalls = [];
  let storeLoaderCalls = 0;
  globalThis.__loadStoreModule = async () => {
    storeLoaderCalls += 1;
    throw new Error('must not load store for Android token');
  };
  globalThis.__loadCoreModule = async () => ({
    invoke: async (command, args) => {
      credentialCalls.push({ command, args });
      return null;
    },
  });
  const { getTokenSync, saveToken } = await loadSecureStorage();

  await saveToken('android-token');

  assert.deepEqual(credentialCalls, [
    {
      command: 'secure_credential_set',
      args: { key: 'auth_token', value: 'android-token' },
    },
  ]);
  assert.equal(storeLoaderCalls, 0);
  assert.equal(getTokenSync(), 'android-token');
});

test('saveUserInfo stores only sanitized user data in Tauri Store', async () => {
  installWindow({}, true);
  const setCalls = [];
  const store = {
    set: async (key, value) => setCalls.push({ key, value }),
    save: async () => {},
  };
  globalThis.__loadStoreModule = async () => ({
    load: async () => store,
  });
  const { saveUserInfo } = await loadSecureStorage();

  await saveUserInfo({
    token: 'must-not-persist',
    username: 'alice',
  });

  assert.deepEqual(setCalls, [
    {
      key: 'user_info',
      value: {
        token: '',
        username: 'alice',
      },
    },
  ]);
});

test('initSecureStorage rejects Tauri read failures without caching partial auth state', async () => {
  installWindow({}, true);
  const store = {
    get: async () => null,
  };
  globalThis.__loadStoreModule = async () => ({
    load: async () => store,
  });
  globalThis.__loadCoreModule = async () => ({
    invoke: async () => {
      throw new Error('credential read failed');
    },
  });
  const { getTokenSync, initSecureStorage } = await loadSecureStorage();
  const originalConsoleError = console.error;
  console.error = () => {};

  try {
    await assert.rejects(initSecureStorage(), /credential read failed/);
  } finally {
    console.error = originalConsoleError;
  }

  assert.equal(getTokenSync(), null);
});

test('initSecureStorage restores Tauri token from native credentials and never reads Store token', async () => {
  installWindow({}, true);
  const storeGetCalls = [];
  const store = {
    get: async (key) => {
      storeGetCalls.push(key);
      if (key === 'user_info') {
        return { username: 'alice', token: '' };
      }
      return 'store-secret-that-must-not-be-read';
    },
  };
  globalThis.__loadStoreModule = async () => ({
    load: async () => store,
  });
  globalThis.__loadCoreModule = async () => ({
    invoke: async (command, args) => {
      assert.equal(command, 'secure_credential_get');
      if (args.key === 'auth_token') return 'credential-token';
      if (args.key === 'refresh_token') return null;
      throw new Error(`unexpected key ${args.key}`);
    },
  });
  const { getTokenSync, initSecureStorage } = await loadSecureStorage();

  await initSecureStorage();

  assert.equal(getTokenSync(), 'credential-token');
  assert.deepEqual(storeGetCalls, ['user_info']);
});

test('initSecureStorage restores Android Tauri token from native credentials and never reads Store token', async () => {
  installWindow({}, true, 'Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36');
  const storeGetCalls = [];
  const store = {
    get: async (key) => {
      storeGetCalls.push(key);
      if (key === 'user_info') return { username: 'android', token: '' };
      return 'store-secret-that-must-not-be-read';
    },
  };
  globalThis.__loadStoreModule = async () => ({
    load: async () => store,
  });
  globalThis.__loadCoreModule = async () => ({
    invoke: async (command, args) => {
      assert.equal(command, 'secure_credential_get');
      if (args.key === 'auth_token') return 'android-credential-token';
      if (args.key === 'refresh_token') return null;
      throw new Error(`unexpected key ${args.key}`);
    },
  });
  const { getTokenSync, initSecureStorage } = await loadSecureStorage();

  await initSecureStorage();

  assert.equal(getTokenSync(), 'android-credential-token');
  assert.deepEqual(storeGetCalls, ['user_info']);
});

test('clearAuthData removes native credentials and sanitized user cache on logout', async () => {
  installWindow({}, true);
  const credentialCalls = [];
  const storeDeleteCalls = [];
  const store = {
    set: async () => {},
    delete: async (key) => storeDeleteCalls.push(key),
    save: async () => {},
  };
  globalThis.__loadStoreModule = async () => ({ load: async () => store });
  globalThis.__loadCoreModule = async () => ({
    invoke: async (command, args) => {
      credentialCalls.push({ command, args });
      return null;
    },
  });
  const { clearAuthData, getTokenSync, saveToken, saveUserInfo } = await loadSecureStorage();

  await saveToken('token-to-remove');
  await saveUserInfo({ token: 'token-to-remove', username: 'alice' });
  await clearAuthData();

  assert.deepEqual(
    credentialCalls.filter(({ command }) => command === 'secure_credential_remove'),
    [
      { command: 'secure_credential_remove', args: { key: 'auth_token' } },
      { command: 'secure_credential_remove', args: { key: 'refresh_token' } },
    ],
  );
  assert.deepEqual(storeDeleteCalls, ['user_info']);
  assert.equal(getTokenSync(), null);
});

test('secureClear removes Android native credentials and Store cache', async () => {
  installWindow({}, true, 'Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36');
  const credentialCalls = [];
  let storeCleared = false;
  const store = {
    clear: async () => {
      storeCleared = true;
    },
    save: async () => {},
  };
  globalThis.__loadStoreModule = async () => ({ load: async () => store });
  globalThis.__loadCoreModule = async () => ({
    invoke: async (command, args) => {
      credentialCalls.push({ command, args });
      return null;
    },
  });
  const { secureClear } = await loadSecureStorage();

  await secureClear();

  assert.deepEqual(credentialCalls, [
    { command: 'secure_credential_remove', args: { key: 'auth_token' } },
    { command: 'secure_credential_remove', args: { key: 'refresh_token' } },
  ]);
  assert.equal(storeCleared, true);
});

test('clearAuthData attempts every removal and clears memory after one native failure', async () => {
  installWindow({}, true);
  const removeCalls = [];
  const storeDeleteCalls = [];
  const store = {
    delete: async (key) => storeDeleteCalls.push(key),
    save: async () => {},
  };
  globalThis.__loadStoreModule = async () => ({ load: async () => store });
  globalThis.__loadCoreModule = async () => ({
    invoke: async (command, args) => {
      if (command === 'secure_credential_set') return null;
      if (command === 'secure_credential_remove') {
        removeCalls.push(args.key);
        if (args.key === 'auth_token') throw new Error('keychain delete failed');
        return null;
      }
      throw new Error(`unexpected command ${command}`);
    },
  });
  const { clearAuthData, getTokenSync, saveToken } = await loadSecureStorage();
  await saveToken('token-to-remove');
  const originalConsoleError = console.error;
  console.error = () => {};

  try {
    await assert.rejects(clearAuthData(), AggregateError);
  } finally {
    console.error = originalConsoleError;
  }

  assert.deepEqual(removeCalls, ['auth_token', 'refresh_token']);
  assert.deepEqual(storeDeleteCalls, ['user_info']);
  assert.equal(getTokenSync(), null);
});
