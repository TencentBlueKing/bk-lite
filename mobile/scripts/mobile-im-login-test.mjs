import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const projectRoot = new URL('../', import.meta.url);

function resolveSpecifier(fromPath, specifier) {
  const target = new URL(specifier, new URL(fromPath, projectRoot));
  let relative = target.pathname.slice(new URL(projectRoot).pathname.length);
  if (!relative.endsWith('.ts') && !relative.endsWith('.tsx')) relative += '.ts';
  return relative;
}

async function loadTypeScriptModule(entryPath) {
  const sources = new Map();

  async function visit(path) {
    if (sources.has(path)) return;
    const source = await readFile(new URL(path, projectRoot), 'utf8');
    const output = ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText;
    sources.set(path, output);
    for (const match of output.matchAll(/from ['"](\.[^'"]+)['"]/g)) {
      await visit(resolveSpecifier(path, match[1]));
    }
  }

  await visit(entryPath);
  const urls = new Map();

  function moduleUrl(path) {
    if (urls.has(path)) return urls.get(path);
    const output = sources.get(path).replace(/from (['"])(\.[^'"]+)\1/g, (_, quote, specifier) => {
      return `from ${quote}${moduleUrl(resolveSpecifier(path, specifier))}${quote}`;
    });
    const url = `data:text/javascript;base64,${Buffer.from(output).toString('base64')}`;
    urls.set(path, url);
    return url;
  }

  return import(moduleUrl(entryPath));
}

const feishuBinding = {
  id: 7,
  name: '飞书',
  provider_key: 'feishu',
  client_login: {
    evidence_modes: ['oauth', 'jsapi'],
    jsapi: { app_id: 'cli_public' },
  },
};

test('non-Feishu environment skips silent login before requesting bindings', async () => {
  const { runSilentImLogin } = await loadTypeScriptModule('src/auth/im-login/shell.ts');
  let loaded = false;

  const outcome = await runSilentImLogin({
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
    loadBindings: async () => {
      loaded = true;
      return [feishuBinding];
    },
    getAuthCode: async () => {
      throw new Error('jsapi should not run');
    },
    exchange: async () => null,
    establishSession: async () => ({ status: 'success', token: 'token' }),
  });

  assert.deepEqual(outcome, { status: 'skipped' });
  assert.equal(loaded, false);
});

test('Feishu workbench silent login exchanges the JSAPI code and opens the shared session', async () => {
  const { runSilentImLogin } = await loadTypeScriptModule('src/auth/im-login/shell.ts');
  const calls = [];

  const outcome = await runSilentImLogin({
    userAgent: 'Mozilla/5.0 Lark/7.18.0 Feishu',
    loadBindings: async () => [feishuBinding],
    getAuthCode: async (binding) => {
      calls.push(['code', binding.id]);
      return { code: 'jsapi-code', evidenceMode: 'jsapi', jsapiCodeType: 'request_access' };
    },
    exchange: async (binding, proof) => {
      calls.push(['exchange', binding.id, proof]);
      return { id: 9, username: 'ada', token: 'backend-token' };
    },
    establishSession: async (loginResult) => {
      calls.push(['session', loginResult.token]);
      return { status: 'success', token: loginResult.token };
    },
  });

  assert.deepEqual(outcome, { status: 'success', token: 'backend-token' });
  assert.deepEqual(calls, [
    ['code', 7],
    ['exchange', 7, { code: 'jsapi-code', evidenceMode: 'jsapi', jsapiCodeType: 'request_access' }],
    ['session', 'backend-token'],
  ]);
});

test('JSAPI failure inside Feishu degrades to the login page', async () => {
  const { runSilentImLogin } = await loadTypeScriptModule('src/auth/im-login/shell.ts');
  let exchanged = false;

  const outcome = await runSilentImLogin({
    userAgent: 'Feishu',
    loadBindings: async () => [feishuBinding],
    getAuthCode: async () => {
      throw Object.assign(new Error('not in client'), { errno: 102 });
    },
    exchange: async () => {
      exchanged = true;
      return null;
    },
    establishSession: async () => ({ status: 'success', token: 'token' }),
  });

  assert.equal(exchanged, false);
  assert.deepEqual(outcome, {
    status: 'degraded',
    notice: { reason: 'jsapi_failed', name: '飞书' },
  });
});

test('Feishu requestAccess code is marked for the JSAPI token exchange', async () => {
  const { requestFeishuAuthCode } = await loadTypeScriptModule('src/auth/im-login/providers/feishu.ts');
  const proof = await requestFeishuAuthCode('cli_public', {
    tt: {
      requestAccess(options) {
        options.success({ code: 'access-code' });
      },
      requestAuthCode() {
        throw new Error('legacy api should stay unused');
      },
    },
  });

  assert.deepEqual(proof, {
    code: 'access-code',
    evidenceMode: 'jsapi',
    jsapiCodeType: 'request_access',
  });
});

test('old Feishu clients fall back from requestAccess errno 103 to requestAuthCode', async () => {
  const { requestFeishuAuthCode, FEISHU_REQUEST_ACCESS_UNSUPPORTED } = await loadTypeScriptModule(
    'src/auth/im-login/providers/feishu.ts',
  );
  const proof = await requestFeishuAuthCode('cli_public', {
    tt: {
      requestAccess(options) {
        options.fail({ errno: FEISHU_REQUEST_ACCESS_UNSUPPORTED });
      },
      requestAuthCode(options) {
        options.success({ code: 'legacy-code' });
      },
    },
  });

  assert.equal(proof.jsapiCodeType, 'request_auth_code');
  assert.equal(proof.code, 'legacy-code');
});

test('requestAccess failure without a client shell does not pretend to be logged in', async () => {
  const { requestFeishuAuthCode } = await loadTypeScriptModule('src/auth/im-login/providers/feishu.ts');

  await assert.rejects(
    requestFeishuAuthCode('cli_public', {
      tt: {
        requestAccess(options) {
          options.fail({ errno: 102, errString: 'not in feishu' });
        },
        requestAuthCode() {
          throw new Error('legacy api should stay unused');
        },
      },
    }),
    (error) => error.errno === 102,
  );
});

test('OAuth return exchanges the stored request and builds the same session payload', async () => {
  const { completeOAuthReturn } = await loadTypeScriptModule('src/auth/im-login/oauth.ts');
  const seen = [];

  const outcome = await completeOAuthReturn({
    pending: { authRequestId: 'auth-1', pollToken: 'poll-1', bindingName: '飞书' },
    returnStatus: 'success',
    fetchStatus: async (pending) => {
      seen.push(pending.authRequestId);
      return {
        status: 'success',
        login_result: { id: 9, username: 'ada', token: 'backend-token' },
      };
    },
    establishSession: async (loginResult) => {
      seen.push(loginResult.token);
      return { status: 'success', token: loginResult.token };
    },
  });

  assert.deepEqual(outcome, { status: 'success', token: 'backend-token' });
  assert.deepEqual(seen, ['auth-1', 'backend-token']);
});

test('OAuth failure redirects back without creating a session', async () => {
  const { completeOAuthReturn } = await loadTypeScriptModule('src/auth/im-login/oauth.ts');
  let fetched = false;

  const outcome = await completeOAuthReturn({
    pending: { authRequestId: 'auth-1', pollToken: 'poll-1', bindingName: '飞书' },
    returnStatus: 'failed',
    fetchStatus: async () => {
      fetched = true;
      return { status: 'success', login_result: { token: 'backend-token', username: 'ada', id: 9 } };
    },
    establishSession: async () => ({ status: 'success', token: 'backend-token' }),
  });

  assert.equal(fetched, false);
  assert.deepEqual(outcome, {
    status: 'degraded',
    notice: { reason: 'oauth_failed', name: '飞书' },
  });
});

test('OAuth return without the pending request degrades', async () => {
  const { completeOAuthReturn } = await loadTypeScriptModule('src/auth/im-login/oauth.ts');
  const outcome = await completeOAuthReturn({
    pending: null,
    returnStatus: '',
    fetchStatus: async () => {
      throw new Error('should not fetch');
    },
    establishSession: async () => ({ status: 'success', token: 'backend-token' }),
  });

  assert.equal(outcome.status, 'degraded');
  assert.equal(outcome.notice.reason, 'oauth_failed');
});

test('login buttons only list bindings that advertise oauth', async () => {
  const { selectOauthBindings, selectJsapiBinding } = await loadTypeScriptModule('src/auth/im-login/bindings.ts');
  const passwordOnly = { id: 1, name: 'AD', provider_key: 'ad', client_login: { evidence_modes: [] } };
  const oauthOnly = { id: 2, name: '微信', provider_key: 'wechat', client_login: { evidence_modes: ['oauth'] } };

  assert.deepEqual(
    selectOauthBindings([passwordOnly, oauthOnly, feishuBinding]).map((item) => item.id),
    [2, 7],
  );
  assert.equal(selectJsapiBinding([passwordOnly, oauthOnly, feishuBinding], 'feishu')?.id, 7);
  assert.equal(selectJsapiBinding([oauthOnly], 'feishu'), null);
});
