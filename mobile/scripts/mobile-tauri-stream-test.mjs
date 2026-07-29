import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const projectRoot = new URL('../', import.meta.url);

async function loadTauriApiProxy() {
  const source = await readFile(new URL('src/utils/tauriApiProxy.ts', projectRoot), 'utf8');
  const moduleSource = source
    .replace(/^import .*?;\n/gm, '')
    .replaceAll("import('@tauri-apps/api/core')", 'globalThis.__loadTauriCore()')
    .replaceAll("import('@tauri-apps/api/event')", 'globalThis.__loadTauriEvent()');
  const prelude = `
    const getUserInfoSync = () => null;
    const getCurrentTeamCookie = () => null;
    const resolveDefaultCurrentTeamId = () => null;
  `;
  const output = ts.transpileModule(`${prelude}\n${moduleSource}`, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;

  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}#${Math.random()}`);
}

async function loadRequestModule(dependencies) {
  const source = await readFile(new URL('src/api/request.ts', projectRoot), 'utf8');
  const moduleSource = source.replace(/^import .*?;\n/gm, '');
  const prelude = `
    const {
      tauriFetch,
      isTauriApp,
      tauriApiStream,
      TauriStreamError,
      getTokenSync,
      clearAuthData,
      withBasePath,
      clearCurrentTeamCookie,
    } = globalThis.__requestDependencies;
  `;
  globalThis.__requestDependencies = dependencies;
  const output = ts.transpileModule(`${prelude}\n${moduleSource}`, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;

  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}#${Math.random()}`);
}

test.afterEach(() => {
  delete globalThis.__loadTauriCore;
  delete globalThis.__loadTauriEvent;
  delete globalThis.__requestDependencies;
  delete globalThis.window;
});

test('Tauri fetch rejects responses that arrive after the request is aborted', async () => {
  class MockChannel {
    onmessage = () => {};
  }

  let resolveInvoke;
  let invokeCalls = 0;
  const invokePending = new Promise((resolve) => {
    resolveInvoke = resolve;
  });
  globalThis.window = { __TAURI_INTERNALS__: {} };
  globalThis.__loadTauriCore = async () => ({
    Channel: MockChannel,
    invoke: async () => {
      invokeCalls += 1;
      return invokePending;
    },
  });

  const { tauriApiFetch } = await loadTauriApiProxy();
  const alreadyAborted = new AbortController();
  alreadyAborted.abort();
  await assert.rejects(
    tauriApiFetch('https://bklite.example.com/api/profile', { signal: alreadyAborted.signal }),
    { name: 'AbortError' },
  );
  assert.equal(invokeCalls, 0);

  const controller = new AbortController();
  const request = tauriApiFetch('https://bklite.example.com/api/profile', {
    signal: controller.signal,
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  controller.abort();
  resolveInvoke({ status: 200, headers: {}, body: '{"ok":true}' });

  await assert.rejects(request, { name: 'AbortError' });
  assert.equal(invokeCalls, 1);
});

test('Tauri stream receives events emitted before the start command returns', async () => {
  class MockChannel {
    onmessage = () => {};
  }

  globalThis.__loadTauriCore = async () => ({
    Channel: MockChannel,
    invoke: async (command, args) => {
      assert.equal(command, 'api_stream_proxy');
      assert.ok(args.onEvent instanceof MockChannel);
      args.onEvent.onmessage({ event: 'chunk', data: 'data: {"text":"fast"}\n' });
      args.onEvent.onmessage({ event: 'end' });
      return 'stream-fast';
    },
  });
  globalThis.__loadTauriEvent = async () => {
    throw new Error('global Tauri events must not be used for request-scoped streams');
  };

  const { tauriApiStream } = await loadTauriApiProxy();
  const chunks = [];
  for await (const chunk of tauriApiStream('https://bklite.example.com/api/stream')) {
    chunks.push(chunk);
  }

  assert.deepEqual(chunks, ['data: {"text":"fast"}\n']);
});

test('Tauri stream 401 uses the shared unauthorized-session path', async () => {
  class MockTauriStreamError extends Error {
    constructor(message, status) {
      super(message);
      this.status = status;
    }
  }

  let unauthorizedCalls = 0;
  const requestModule = await loadRequestModule({
    tauriFetch: async () => { throw new Error('unexpected non-stream request'); },
    isTauriApp: () => true,
    tauriApiStream: async function* () {
      throw new MockTauriStreamError('HTTP Error: 401', 401);
    },
    TauriStreamError: MockTauriStreamError,
    getTokenSync: () => 'expired-token',
    clearAuthData: async () => {},
    withBasePath: (path) => path,
    clearCurrentTeamCookie: () => {},
  });
  requestModule.setUnauthorizedHandler(async () => {
    unauthorizedCalls += 1;
  });

  await assert.rejects(async () => {
    for await (const _event of requestModule.apiStream('/chat', {})) {
      // A 401 stream must not yield application events.
    }
  }, requestModule.UnauthorizedRequestError);
  assert.equal(unauthorizedCalls, 1);
});

test('apiStream preserves a data prefix split from its JSON payload', async () => {
  const requestModule = await loadRequestModule({
    tauriFetch: async () => { throw new Error('unexpected non-stream request'); },
    isTauriApp: () => true,
    tauriApiStream: async function* () {
      yield 'data:\n';
      yield '{"type":"RUN_FINISHED"}\n';
      yield 'data: [DONE]\n\n';
    },
    TauriStreamError: class extends Error {},
    getTokenSync: () => 'valid-token',
    clearAuthData: async () => {},
    withBasePath: (path) => path,
    clearCurrentTeamCookie: () => {},
  });

  const events = [];
  for await (const event of requestModule.apiStream('/chat', {})) {
    events.push(event);
  }

  assert.deepEqual(events, [{ type: 'RUN_FINISHED' }]);
});

test('a delayed 401 from an old token cannot clear a newer login', async () => {
  let resolveResponse;
  const responsePromise = new Promise((resolve) => {
    resolveResponse = resolve;
  });
  let unauthorizedCalls = 0;
  const requestModule = await loadRequestModule({
    tauriFetch: async () => responsePromise,
    isTauriApp: () => true,
    tauriApiStream: async function* () {},
    TauriStreamError: class extends Error {},
    getTokenSync: () => 'old-token',
    clearAuthData: async () => {},
    withBasePath: (path) => path,
    clearCurrentTeamCookie: () => {},
  });
  requestModule.setRuntimeAuthToken('old-token');
  requestModule.setUnauthorizedHandler(async () => {
    unauthorizedCalls += 1;
  });

  const oldRequest = requestModule.apiRequest('/profile');
  requestModule.setRuntimeAuthToken('new-token');
  resolveResponse(new Response('', { status: 401 }));

  await assert.rejects(oldRequest, requestModule.UnauthorizedRequestError);
  assert.equal(unauthorizedCalls, 0);
});

test('concurrent 401 responses clear one authentication generation only once', async () => {
  let finishUnauthorized;
  const unauthorizedPending = new Promise((resolve) => {
    finishUnauthorized = resolve;
  });
  let unauthorizedCalls = 0;
  const requestModule = await loadRequestModule({
    tauriFetch: async () => new Response('', { status: 401 }),
    isTauriApp: () => true,
    tauriApiStream: async function* () {},
    TauriStreamError: class extends Error {},
    getTokenSync: () => 'same-token',
    clearAuthData: async () => {},
    withBasePath: (path) => path,
    clearCurrentTeamCookie: () => {},
  });
  requestModule.setRuntimeAuthToken('same-token');
  requestModule.setUnauthorizedHandler(async () => {
    unauthorizedCalls += 1;
    await unauthorizedPending;
  });

  const first = requestModule.apiRequest('/first');
  const second = requestModule.apiRequest('/second');
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(unauthorizedCalls, 1);
  finishUnauthorized();

  await Promise.all([
    assert.rejects(first, requestModule.UnauthorizedRequestError),
    assert.rejects(second, requestModule.UnauthorizedRequestError),
  ]);
  assert.equal(unauthorizedCalls, 1);
});
