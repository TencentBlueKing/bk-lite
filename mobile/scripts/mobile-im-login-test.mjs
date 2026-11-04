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

test('string errno 103 falls back from requestAccess to requestAuthCode', async () => {
  const { requestFeishuAuthCode } = await loadTypeScriptModule('src/auth/im-login/providers/feishu.ts');

  for (const errno of ['103', ' 103 ', '103.0']) {
    const proof = await requestFeishuAuthCode('cli_public', {
      tt: {
        requestAccess(options) {
          options.fail({ errno });
        },
        requestAuthCode(options) {
          options.success({ code: `legacy-${errno.trim()}` });
        },
      },
    });
    assert.equal(proof.jsapiCodeType, 'request_auth_code');
    assert.equal(proof.code, `legacy-${errno.trim()}`);
  }
});

test('string errno other than 103 does not fall back to requestAuthCode', async () => {
  const { requestFeishuAuthCode } = await loadTypeScriptModule('src/auth/im-login/providers/feishu.ts');

  await assert.rejects(
    requestFeishuAuthCode('cli_public', {
      tt: {
        requestAccess(options) {
          options.fail({ errno: '102' });
        },
        requestAuthCode() {
          throw new Error('legacy api should stay unused');
        },
      },
    }),
    (error) => error.errno === '102',
  );
});

test('requestAccess and requestAuthCode time out instead of hanging', async () => {
  const { requestFeishuAuthCode } = await loadTypeScriptModule('src/auth/im-login/providers/feishu.ts');
  let legacyCalled = false;

  await assert.rejects(
    requestFeishuAuthCode('cli_public', {
      tt: {
        requestAccess() {},
        requestAuthCode() {
          legacyCalled = true;
        },
      },
    }, 20),
    (error) => error.message === 'feishu_jsapi_timeout',
  );
  assert.equal(legacyCalled, false);

  await assert.rejects(
    requestFeishuAuthCode('cli_public', {
      tt: {
        requestAccess(options) {
          options.fail({ errno: '103' });
        },
        requestAuthCode() {},
      },
    }, 20),
    (error) => error.message === 'feishu_jsapi_timeout',
  );
});

test('h5sdk.ready still times out before requestAccess', async () => {
  const { requestFeishuAuthCode } = await loadTypeScriptModule('src/auth/im-login/providers/feishu.ts');
  let requested = false;

  await assert.rejects(
    requestFeishuAuthCode('cli_public', {
      h5sdk: { ready() {} },
      tt: {
        requestAccess() {
          requested = true;
        },
      },
    }, 20),
    (error) => error.message === 'feishu_ready_timeout',
  );
  assert.equal(requested, false);
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

test('session keeps otp and temporary password off the password sign-in path', async () => {
  const { establishH5SessionFromLoginResult, noticeForExternalSession } = await loadTypeScriptModule(
    'src/auth/im-login/session.ts',
  );
  let signedOut = 0;
  const dependencies = {
    signIn: async () => {
      throw new Error('should not open a password session');
    },
    getSession: async () => {
      throw new Error('should not read a password session');
    },
    signOut: async () => {
      signedOut += 1;
    },
  };

  const reset = await establishH5SessionFromLoginResult(
    { temporary_pwd: true, token: 'temp-token', username: 'ada' },
    dependencies,
  );
  const otp = await establishH5SessionFromLoginResult(
    { require_otp: true, token: 'otp-token', username: 'ada' },
    dependencies,
  );

  assert.deepEqual(reset, { status: 'password-reset-required' });
  assert.deepEqual(otp, { status: 'otp-required' });
  assert.equal(signedOut, 2);
  assert.equal(noticeForExternalSession(reset.status, '飞书').reason, 'password_reset_required');
  assert.equal(noticeForExternalSession(otp.status, '飞书').reason, 'otp_required');
});

test('session treats enable_otp alone as a normal token session', async () => {
  const { establishH5SessionFromLoginResult } = await loadTypeScriptModule('src/auth/im-login/session.ts');
  const calls = [];
  const result = await establishH5SessionFromLoginResult(
    { enable_otp: true, token: 'backend-token', username: 'ada', id: 9 },
    {
      signIn: async (provider, options) => {
        calls.push(['signIn', provider, JSON.parse(String(options.userData))]);
        return { ok: true };
      },
      getSession: async () => ({ user: { token: 'backend-token' } }),
      signOut: async () => {
        throw new Error('should not sign out');
      },
    },
  );

  assert.deepEqual(result, { status: 'success', token: 'backend-token' });
  assert.equal(calls[0][0], 'signIn');
  assert.equal(calls[0][2].enable_otp, true);
  assert.equal(calls[0][2].token, 'backend-token');
});

test('otp and temporary password use the desktop prompts instead of a password-only notice', async () => {
  const { runSilentImLogin } = await loadTypeScriptModule('src/auth/im-login/shell.ts');
  const { completeOAuthReturn } = await loadTypeScriptModule('src/auth/im-login/oauth.ts');
  const { presentationForLoginNotice } = await loadTypeScriptModule('src/auth/im-login/notices.ts');
  const zh = JSON.parse(await readFile(new URL('../src/locales/zh.json', import.meta.url), 'utf8'));
  const en = JSON.parse(await readFile(new URL('../src/locales/en.json', import.meta.url), 'utf8'));

  const silentBase = {
    userAgent: 'Feishu',
    loadBindings: async () => [feishuBinding],
    getAuthCode: async () => ({ code: 'jsapi-code', evidenceMode: 'jsapi', jsapiCodeType: 'request_access' }),
    exchange: async () => ({ id: 9, username: 'ada', token: 'backend-token', temporary_pwd: true }),
  };
  const otp = await runSilentImLogin({
    ...silentBase,
    establishSession: async () => ({ status: 'otp-required' }),
  });
  const reset = await runSilentImLogin({
    ...silentBase,
    establishSession: async () => ({ status: 'password-reset-required' }),
  });
  const unavailable = await runSilentImLogin({
    ...silentBase,
    establishSession: async () => ({ status: 'service-unavailable' }),
  });

  assert.deepEqual(otp.notice, { reason: 'otp_required', name: '飞书' });
  assert.deepEqual(reset.notice, { reason: 'password_reset_required', name: '飞书' });
  assert.deepEqual(unavailable.notice, { reason: 'session_failed', name: '飞书' });
  assert.deepEqual(presentationForLoginNotice('otp_required'), { type: 'otp' });
  assert.deepEqual(presentationForLoginNotice('password_reset_required'), { type: 'password-reset' });
  assert.deepEqual(presentationForLoginNotice('session_failed'), {
    type: 'toast',
    messageKey: 'login.sessionFailed',
  });

  const oauthOtp = await completeOAuthReturn({
    pending: { authRequestId: 'auth-1', pollToken: 'poll-1', bindingName: '飞书' },
    returnStatus: 'success',
    fetchStatus: async () => ({ status: 'success', login_result: { token: 'backend-token' } }),
    establishSession: async () => ({ status: 'otp-required' }),
  });
  assert.deepEqual(oauthOtp.notice, { reason: 'otp_required', name: '飞书' });

  assert.match(zh.login.twoFactorHint, /桌面端/);
  assert.match(zh.login.passwordResetHint, /桌面端/);
  assert.match(en.login.twoFactorHint, /desktop/i);
  assert.match(en.login.passwordResetHint, /desktop/i);
  for (const key of ['silentFailed', 'sessionFailed', 'oauthFailed']) {
    assert.equal(zh.login[key].includes('密码'), false, key);
    assert.equal(en.login[key].toLowerCase().includes('password'), false, key);
  }
});

test('external sign-in label skips a second 登录 when the binding name already has one', async () => {
  const { externalSignInMessageId } = await loadTypeScriptModule('src/auth/im-login/external-sign-in-label.ts');
  const zh = JSON.parse(await readFile(new URL('../src/locales/zh.json', import.meta.url), 'utf8'));
  const en = JSON.parse(await readFile(new URL('../src/locales/en.json', import.meta.url), 'utf8'));
  assert.equal(externalSignInMessageId('飞书'), 'login.externalSignIn');
  assert.equal(externalSignInMessageId('企微登陆'), 'login.externalUse');
  assert.equal(externalSignInMessageId('企业微信登录'), 'login.externalUse');
  assert.equal(externalSignInMessageId('WeCom Login'), 'login.externalUse');
  assert.equal(zh.login.externalSignIn, '使用{name}登录');
  assert.equal(zh.login.externalUse, '使用{name}');
  assert.equal(en.login.externalUse, 'Use {name}');
});

test('login page reuses the sign-in button style and method switcher', async () => {
  const { LOGIN_ACTION_BUTTON_CLASS, loginActionButtonStyle } = await loadTypeScriptModule(
    'src/auth/im-login/login-button-style.ts',
  );
  const page = await readFile(new URL('../src/app/login/page.tsx', import.meta.url), 'utf8');

  assert.equal(LOGIN_ACTION_BUTTON_CLASS, 'w-full h-11 rounded-lg shadow-sm');
  assert.deepEqual(loginActionButtonStyle(false), {
    backgroundColor: '#2563eb',
    color: '#ffffff',
    borderRadius: '0.5rem',
    fontSize: '16px',
    fontWeight: '500',
    '--background-color': '#2563eb',
    '--border-color': '#2563eb',
    '--text-color': '#ffffff',
    '--border-radius': '0.5rem',
  });
  assert.equal(loginActionButtonStyle(true).backgroundColor, '#e5e7eb');
  assert.equal(page.includes('loginActionButtonStyle'), true);
  assert.equal(page.includes('externalSignInMessageId'), true);
  assert.equal(page.includes('login.methodsTitle'), true);
  assert.equal(page.includes('selectMobileLoginBindings'), false);
  assert.equal(page.includes('loadMobileLoginBindings'), true);
  assert.equal(page.includes('更多'), false);
  assert.equal(page.includes('ExternalLoginButtons'), false);
});

test('mobile login methods keep builtin password and oauth-capable bindings', async () => {
  const {
    selectMobileLoginBindings,
    resolveInitialMobileBindingId,
    resolveSelectedMobileBinding,
    isBuiltinLoginBinding,
  } = await loadTypeScriptModule('src/auth/im-login/bindings.ts');
  const builtin = { id: 1, name: '平台账号密码登录', provider_key: 'bk_lite_builtin', icon: 'zhanghaomima', client_login: { evidence_modes: [] } };
  const wechat = { id: 2, name: '微信', provider_key: 'wechat', icon: 'wechat', client_login: { evidence_modes: [] } };
  const feishu = { id: 3, name: '飞书', provider_key: 'feishu', icon: 'feishu', client_login: { evidence_modes: ['oauth', 'jsapi'], jsapi: { app_id: 'cli_x' } } };
  const wecom = { id: 4, name: '企微登陆', provider_key: 'wecom', icon: 'wecom', client_login: { evidence_modes: ['oauth'] } };
  // System browser: WeCom oauth is not usable, so hide it.
  const methods = selectMobileLoginBindings([builtin, wechat, feishu, wecom], 'Mozilla/5.0 (iPhone)');
  assert.deepEqual(methods.map((item) => item.id), [1, 3]);
  assert.equal(resolveInitialMobileBindingId(methods), 1);
  assert.equal(resolveInitialMobileBindingId([feishu, builtin, wecom]), 1);

  assert.equal(resolveSelectedMobileBinding(methods, 3)?.id, 3);
  assert.equal(resolveSelectedMobileBinding(methods, 99)?.id, 1);
  assert.equal(isBuiltinLoginBinding(builtin), true);
  assert.equal(isBuiltinLoginBinding(feishu), false);
});

test('WeCom login method only appears inside the WeCom container', async () => {
  const { selectMobileLoginBindings, isMobileBindingSupportedOnClient } = await loadTypeScriptModule(
    'src/auth/im-login/bindings.ts',
  );
  const builtin = { id: 1, name: '平台账号密码登录', provider_key: 'bk_lite_builtin', client_login: { evidence_modes: [] } };
  const feishu = { id: 3, name: '飞书', provider_key: 'feishu', client_login: { evidence_modes: ['oauth'] } };
  const wecom = { id: 4, name: '企微登陆', provider_key: 'wecom', client_login: { evidence_modes: ['oauth'] } };
  const browserUa = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15';
  const wecomUa = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 wxwork/4.1.0 MicroMessenger/7.0.1';

  assert.equal(isMobileBindingSupportedOnClient(wecom, browserUa), false);
  assert.equal(isMobileBindingSupportedOnClient(wecom, wecomUa), true);
  assert.equal(isMobileBindingSupportedOnClient(feishu, browserUa), true);
  assert.deepEqual(
    selectMobileLoginBindings([builtin, feishu, wecom], browserUa).map((item) => item.id),
    [1, 3],
  );
  assert.deepEqual(
    selectMobileLoginBindings([builtin, feishu, wecom], wecomUa).map((item) => item.id),
    [1, 3, 4],
  );
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

const wecomBinding = {
  id: 8,
  name: '企业微信',
  provider_key: 'wecom',
  client_login: { evidence_modes: ['oauth'] },
};

const wecomUserAgent = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 wxwork/4.1.0 MicroMessenger/7.0.1';

test('mobile OAuth start asks for the oauth channel without naming a vendor', async () => {
  const { buildExternalLoginStartBody, OAUTH_LOGIN_CHANNEL } = await loadTypeScriptModule('src/auth/im-login/oauth.ts');
  const body = buildExternalLoginStartBody({
    bindingId: 8,
    callbackUrl: '/mobile/h5/',
    redirectOrigin: 'https://bk.example',
    resultPath: '/mobile/h5/auth/external',
  });

  assert.equal(body.login_channel, 'oauth');
  assert.equal(body.login_channel, OAUTH_LOGIN_CHANNEL);
  assert.equal(body.binding_id, 8);
  assert.equal(body.result_path, '/mobile/h5/auth/external');
  assert.equal(JSON.stringify(body).includes('wecom'), false);
  assert.equal(JSON.stringify(body).includes('feishu'), false);
});

test('OAuth buttons include every binding that advertises oauth', async () => {
  const { selectOauthBindings, selectProviderOauthBinding, selectJsapiBinding } = await loadTypeScriptModule(
    'src/auth/im-login/bindings.ts',
  );
  const passwordOnly = { id: 1, name: '账号密码', provider_key: 'ad', client_login: { evidence_modes: [] } };

  assert.deepEqual(
    selectOauthBindings([passwordOnly, wecomBinding, feishuBinding]).map((item) => item.id),
    [8, 7],
  );
  assert.equal(selectProviderOauthBinding([wecomBinding, feishuBinding], 'wecom')?.name, '企业微信');
  assert.equal(selectJsapiBinding([wecomBinding, feishuBinding], 'wecom'), null);
  assert.equal(selectJsapiBinding([wecomBinding, feishuBinding], 'feishu')?.id, 7);
});

test('WeCom workbench silently starts OAuth and does not call JSAPI', async () => {
  const { runSilentImLogin } = await loadTypeScriptModule('src/auth/im-login/shell.ts');
  const calls = [];

  const outcome = await runSilentImLogin({
    userAgent: wecomUserAgent,
    loadBindings: async () => [feishuBinding, wecomBinding],
    getAuthCode: async () => {
      throw new Error('jsapi should not run');
    },
    exchange: async () => {
      throw new Error('exchange should not run');
    },
    startOauth: async (binding) => {
      calls.push(binding.id);
      return true;
    },
    establishSession: async () => ({ status: 'success', token: 'token' }),
  });

  assert.deepEqual(outcome, { status: 'redirecting' });
  assert.deepEqual(calls, [8]);
});

test('WeCom OAuth start failure degrades back to the login page', async () => {
  const { runSilentImLogin } = await loadTypeScriptModule('src/auth/im-login/shell.ts');
  let exchanged = false;

  const refused = await runSilentImLogin({
    userAgent: 'wxwork/4.1.0',
    loadBindings: async () => [wecomBinding],
    getAuthCode: async () => {
      throw new Error('jsapi should not run');
    },
    exchange: async () => {
      exchanged = true;
      return null;
    },
    startOauth: async () => false,
    establishSession: async () => ({ status: 'success', token: 'token' }),
  });
  const thrown = await runSilentImLogin({
    userAgent: 'wxwork/4.1.0',
    loadBindings: async () => [wecomBinding],
    getAuthCode: async () => {
      throw new Error('jsapi should not run');
    },
    exchange: async () => null,
    startOauth: async () => {
      throw new Error('network');
    },
    establishSession: async () => ({ status: 'success', token: 'token' }),
  });

  assert.equal(exchanged, false);
  assert.deepEqual(refused, {
    status: 'degraded',
    notice: { reason: 'oauth_failed', name: '企业微信' },
  });
  assert.deepEqual(thrown.notice, { reason: 'oauth_failed', name: '企业微信' });
});

test('personal WeChat and a normal mobile browser do not auto-start WeCom OAuth', async () => {
  const { runSilentImLogin } = await loadTypeScriptModule('src/auth/im-login/shell.ts');

  for (const userAgent of [
    'Mozilla/5.0 MicroMessenger/8.0.0',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)',
  ]) {
    let loaded = false;
    const outcome = await runSilentImLogin({
      userAgent,
      loadBindings: async () => {
        loaded = true;
        return [wecomBinding];
      },
      getAuthCode: async () => {
        throw new Error('jsapi should not run');
      },
      exchange: async () => null,
      startOauth: async () => {
        throw new Error('oauth should not start');
      },
      establishSession: async () => ({ status: 'success', token: 'token' }),
    });
    assert.deepEqual(outcome, { status: 'skipped' });
    assert.equal(loaded, false, userAgent);
  }
});

test('WeCom container without an oauth binding stays on the login page', async () => {
  const { runSilentImLogin } = await loadTypeScriptModule('src/auth/im-login/shell.ts');
  let started = false;
  const outcome = await runSilentImLogin({
    userAgent: 'wxwork/4.1.0',
    loadBindings: async () => [{ id: 3, name: '企业微信', provider_key: 'wecom', client_login: { evidence_modes: [] } }],
    getAuthCode: async () => {
      throw new Error('jsapi should not run');
    },
    exchange: async () => null,
    startOauth: async () => {
      started = true;
      return true;
    },
    establishSession: async () => ({ status: 'success', token: 'token' }),
  });

  assert.deepEqual(outcome, { status: 'skipped' });
  assert.equal(started, false);
});

test('Feishu workbench still uses JSAPI when a WeCom OAuth binding also exists', async () => {
  const { runSilentImLogin } = await loadTypeScriptModule('src/auth/im-login/shell.ts');
  let started = false;

  const outcome = await runSilentImLogin({
    userAgent: 'Mozilla/5.0 Lark/7.18.0 Feishu',
    loadBindings: async () => [wecomBinding, feishuBinding],
    getAuthCode: async () => ({ code: 'jsapi-code', evidenceMode: 'jsapi', jsapiCodeType: 'request_access' }),
    exchange: async (_binding, proof) => ({ id: 9, username: 'ada', token: proof.code }),
    startOauth: async () => {
      started = true;
      return true;
    },
    establishSession: async (loginResult) => ({ status: 'success', token: loginResult.token }),
  });

  assert.deepEqual(outcome, { status: 'success', token: 'jsapi-code' });
  assert.equal(started, false);
});
