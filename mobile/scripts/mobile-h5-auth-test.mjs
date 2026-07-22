import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const projectRoot = new URL('../', import.meta.url);

async function loadTypeScriptModule(path) {
  const source = await readFile(new URL(path, projectRoot), 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(output).toString('base64')}`;
  return import(moduleUrl);
}

test('H5 login creates a credentials session and returns only the runtime token', async () => {
  const { loginWithH5Session } = await loadTypeScriptModule('src/auth/h5Auth.ts');
  const calls = [];

  const result = await loginWithH5Session(
    { username: 'alice', password: 'secret', domain: 'domain.com' },
    {
      signIn: async (provider, options) => {
        calls.push({ provider, options });
        return { ok: true, status: 200, error: null, url: null };
      },
      getSession: async () => ({ user: { token: 'backend-jwt' } }),
    },
  );

  assert.deepEqual(result, { status: 'success', token: 'backend-jwt' });
  assert.equal(calls[0].provider, 'credentials');
  assert.deepEqual(calls[0].options, {
    username: 'alice',
    password: 'secret',
    domain: 'domain.com',
    redirect: false,
  });
});

test('H5 login maps the existing Web CredentialsSignin error without creating a session', async () => {
  const { loginWithH5Session } = await loadTypeScriptModule('src/auth/h5Auth.ts');
  let getSessionCalled = false;
  const result = await loginWithH5Session(
    { username: 'alice', password: 'wrong', domain: 'domain.com' },
    {
      signIn: async () => ({ ok: false, status: 401, error: 'CredentialsSignin', url: null }),
      getSession: async () => {
        getSessionCalled = true;
        return null;
      },
    },
  );

  assert.deepEqual(result, { status: 'invalid-credentials' });
  assert.equal(getSessionCalled, false);
});

test('H5 login rejects a temporary-password session exposed by existing Web NextAuth', async () => {
  const { loginWithH5Session } = await loadTypeScriptModule('src/auth/h5Auth.ts');
  const result = await loginWithH5Session(
    { username: 'alice', password: 'temporary', domain: 'domain.com' },
    {
      signIn: async () => ({ ok: true, status: 200, error: null, url: null }),
      getSession: async () => ({
        user: { token: 'temporary-token', temporary_pwd: true },
      }),
    },
  );

  assert.deepEqual(result, { status: 'password-reset-required' });
});

test('H5 login rejects an existing Web session without a backend token as OTP challenge', async () => {
  const { loginWithH5Session } = await loadTypeScriptModule('src/auth/h5Auth.ts');
  const result = await loginWithH5Session(
    { username: 'alice', password: 'secret', domain: 'domain.com' },
    {
      signIn: async () => ({ ok: true, status: 200, error: null, url: null }),
      getSession: async () => ({ user: { username: 'alice' } }),
    },
  );

  assert.deepEqual(result, { status: 'otp-required' });
});

test('H5 session restore clears an incomplete NextAuth session', async () => {
  const { restoreH5Session } = await loadTypeScriptModule('src/auth/h5Auth.ts');
  let clearSessionCalls = 0;

  assert.equal(
    await restoreH5Session({
      getSession: async () => ({ user: { username: 'alice' } }),
      clearSession: async () => {
        clearSessionCalls += 1;
      },
    }),
    null,
  );
  assert.equal(clearSessionCalls, 1);
});

test('H5 session restore leaves an anonymous browser without a session untouched', async () => {
  const { restoreH5Session } = await loadTypeScriptModule('src/auth/h5Auth.ts');
  let clearSessionCalls = 0;

  assert.equal(
    await restoreH5Session({
      getSession: async () => null,
      clearSession: async () => {
        clearSessionCalls += 1;
      },
    }),
    null,
  );
  assert.equal(clearSessionCalls, 0);
});

test('H5 backend session rejection clears NextAuth before local authentication state', async () => {
  const { clearRejectedH5Session } = await loadTypeScriptModule('src/auth/h5Auth.ts');
  const calls = [];

  await clearRejectedH5Session({
    clearSession: async () => {
      calls.push('nextauth');
    },
    resetLocalState: async () => {
      calls.push('local');
    },
  });

  assert.deepEqual(calls, ['nextauth', 'local']);
});

test('AuthContext clears rejected H5 sessions after restore and fresh login validation', async () => {
  const source = await readFile(new URL('src/context/auth.tsx', projectRoot), 'utf8');
  const rejectedSessionCleanupCalls = source.match(/await clearRejectedSession\(\);/g) || [];

  assert.match(source, /throw new RejectedSessionError\(\)/);
  assert.equal(rejectedSessionCleanupCalls.length, 2);
});

test('Tauri request never falls back to browser fetch after the Rust proxy rejects it', async () => {
  const source = await readFile(new URL('src/utils/tauriFetch.ts', projectRoot), 'utf8');
  const testableSource = source.replace(
    "import { tauriApiFetch } from './tauriApiProxy';",
    'const tauriApiFetch = globalThis.__tauriApiFetch;',
  );
  const output = ts.transpileModule(testableSource, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;

  const originalWindow = globalThis.window;
  const originalFetch = globalThis.fetch;
  let browserFetchCalls = 0;
  globalThis.window = { __TAURI_INTERNALS__: {} };
  globalThis.__tauriApiFetch = async () => {
    throw new Error('host is not allowlisted');
  };
  globalThis.fetch = async () => {
    browserFetchCalls += 1;
    return new Response();
  };

  try {
    const moduleUrl = `data:text/javascript;base64,${Buffer.from(output).toString('base64')}#${Date.now()}`;
    const { tauriFetch } = await import(moduleUrl);
    await assert.rejects(
      () => tauriFetch('https://blocked.example.com/api'),
      /host is not allowlisted/,
    );
    assert.equal(browserFetchCalls, 0);
  } finally {
    globalThis.window = originalWindow;
    globalThis.fetch = originalFetch;
    delete globalThis.__tauriApiFetch;
  }
});

test('H5 logout clears NextAuth even when backend revocation fails', async () => {
  const { logoutH5Session } = await loadTypeScriptModule('src/auth/h5Auth.ts');
  const calls = [];

  const result = await logoutH5Session({
    federatedLogout: async () => {
      calls.push('revoke');
      throw new Error('network failure');
    },
    signOut: async (options) => {
      calls.push({ signOut: options });
    },
  });

  assert.deepEqual(calls, ['revoke', { signOut: { redirect: false } }]);
  assert.deepEqual(result, { backendLogoutAccepted: false });
});

test('H5 logout only reports whether the existing Web route accepted the request', async () => {
  const { logoutH5Session } = await loadTypeScriptModule('src/auth/h5Auth.ts');
  const result = await logoutH5Session({
    federatedLogout: async () => ({ ok: true }),
    signOut: async () => undefined,
  });

  assert.deepEqual(result, { backendLogoutAccepted: true });
  assert.equal('revoked' in result, false);
});

test('login UI and AuthContext block submissions until session initialization finishes', async () => {
  const [pageSource, contextSource] = await Promise.all([
    readFile(new URL('src/app/login/page.tsx', projectRoot), 'utf8'),
    readFile(new URL('src/context/auth.tsx', projectRoot), 'utf8'),
  ]);

  assert.match(pageSource, /const \{ login, isInitializing \} = useAuth\(\)/);
  assert.match(pageSource, /if \(isInitializing\) return/);
  assert.match(pageSource, /disabled=\{isLoading \|\| isInitializing/);
  assert.match(contextSource, /if \(isInitializing\) return \{ status: 'service-unavailable' \}/);
});

test('H5 runtime token selection never falls back to stored JWT after initialization', async () => {
  const source = await readFile(new URL('src/api/request.ts', projectRoot), 'utf8');
  const sourceFile = ts.createSourceFile(
    'request.ts',
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  const declaration = sourceFile.statements.find(
    (node) => ts.isFunctionDeclaration(node) && node.name?.text === 'resolveApiAuthToken',
  );

  assert.ok(declaration, 'resolveApiAuthToken must be declared in request.ts');
  const output = ts.transpileModule(
    `${declaration.getText(sourceFile)}\nexport { resolveApiAuthToken };`,
    { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } },
  ).outputText;
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(output).toString('base64')}`;
  const { resolveApiAuthToken } = await import(moduleUrl);

  assert.equal(resolveApiAuthToken(undefined, 'stored-token'), 'stored-token');
  assert.equal(resolveApiAuthToken(null, 'stored-token'), null);
  assert.equal(resolveApiAuthToken('runtime-token', 'stored-token'), 'runtime-token');
});

test('request module defaults to no browser token before auth initialization', async () => {
  const source = await readFile(new URL('src/api/request.ts', projectRoot), 'utf8');
  const sourceFile = ts.createSourceFile(
    'request.ts',
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  const statement = sourceFile.statements.find(
    (node) => ts.isVariableStatement(node)
      && node.declarationList.declarations.some(
        (declaration) => ts.isIdentifier(declaration.name)
          && declaration.name.text === 'runtimeAuthToken',
      ),
  );
  const declaration = statement?.declarationList.declarations.find(
    (node) => ts.isIdentifier(node.name) && node.name.text === 'runtimeAuthToken',
  );

  assert.equal(declaration?.initializer?.kind, ts.SyntaxKind.NullKeyword);
});

test('browser user cache removes the backend JWT', async () => {
  const { sanitizeBrowserUserInfo } = await loadTypeScriptModule('src/utils/secureStorage.ts');
  const cachedUser = sanitizeBrowserUserInfo({
    id: 7,
    username: 'alice',
    token: 'backend-jwt',
  });

  assert.equal(cachedUser.token, '');
  assert.equal(JSON.stringify(cachedUser).includes('backend-jwt'), false);
});
