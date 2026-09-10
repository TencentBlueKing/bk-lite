import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  getLegacyThirdLoginCode,
  toSafeRelativeCallbackUrl,
} from '../src/utils/authRedirect';
import { PORTAL_HOME_PATH } from '../src/utils/route';
import { requestLegacyThirdLoginAuthorize } from '../src/utils/legacyThirdLogin';
import { isLegacyThirdLoginExchangePath } from '../src/app/(core)/api/proxy/[...path]/legacyThirdLoginCors';

function run(name: string, fn: () => void | Promise<void>) {
  return Promise.resolve(fn()).then(() => {
    console.log(`  ✓ ${name}`);
  });
}

async function main() {
  await run('keeps relative callback paths unchanged', () => {
    assert.equal(toSafeRelativeCallbackUrl('/monitor/events?tab=detail'), '/monitor/events?tab=detail');
  });

  await run('converts same-origin absolute callback URL into relative path', () => {
    assert.equal(
      toSafeRelativeCallbackUrl('https://bk-lite.example.com/monitor/events?tab=detail#panel', 'https://bk-lite.example.com'),
      '/monitor/events?tab=detail#panel',
    );
  });

  await run('rejects cross-origin absolute callback URL', () => {
    assert.equal(
      toSafeRelativeCallbackUrl('https://attacker.example.com/steal?token=1', 'https://bk-lite.example.com'),
      PORTAL_HOME_PATH,
    );
  });

  await run('rejects protocol-relative callback URL', () => {
    assert.equal(toSafeRelativeCallbackUrl('//attacker.example.com/steal'), PORTAL_HOME_PATH);
  });

  await run('extracts the legacy third login code from an external callback URL', () => {
    assert.equal(
      getLegacyThirdLoginCode('http://localhost:3001/playground?third_login_code=legacy-code'),
      'legacy-code',
    );
  });

  await run('does not extract a legacy third login code from a relative callback URL', () => {
    assert.equal(getLegacyThirdLoginCode('/playground?third_login_code=legacy-code'), undefined);
  });

  await run('authorize helper falls back in-site when the server rejects the callback host', async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async () => new Response(JSON.stringify({ result: false, message: 'no' }), { status: 400 })) as typeof fetch;
    try {
      const target = await requestLegacyThirdLoginAuthorize({
        callbackUrl: 'http://attacker.example/cb?third_login_code=x',
        thirdLoginCode: 'x',
        token: 'jwt-token-sentinel-value',
      });
      assert.equal(target, PORTAL_HOME_PATH);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  await run('authorize helper uses server-provided redirect_url without appending token', async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async () => new Response(
      JSON.stringify({ redirect_url: 'https://bklite.ai/playground?third_login_code=state&bk_lite_code=once' }),
      { status: 200 },
    )) as typeof fetch;
    try {
      const target = await requestLegacyThirdLoginAuthorize({
        callbackUrl: 'https://bklite.ai/playground?third_login_code=state',
        thirdLoginCode: 'state',
        token: 'jwt-token-sentinel-value',
      });
      assert.equal(target, 'https://bklite.ai/playground?third_login_code=state&bk_lite_code=once');
      assert.doesNotMatch(target, /token=/);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  await run('proxy only forwards CORS preflight for the exchange endpoint', () => {
    assert.equal(
      isLegacyThirdLoginExchangePath('/api/proxy/core/api/legacy_third_login/exchange/'),
      true,
    );
    assert.equal(
      isLegacyThirdLoginExchangePath('/api/proxy/core/api/legacy_third_login/exchange'),
      true,
    );
    assert.equal(isLegacyThirdLoginExchangePath('/api/proxy/core/api/login_info/'), false);
    assert.equal(isLegacyThirdLoginExchangePath('/api/proxy/core/api/login/'), false);
    const route = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), '..', 'src/app/(core)/api/proxy/[...path]/route.ts'),
      'utf8',
    );
    assert.equal(route.includes('withLegacyThirdLoginCors'), false);
    assert.match(route, /isLegacyThirdLoginExchangePath/);
  });

  await run('repository no longer concatenates token onto non-same-origin URLs', () => {
    const root = join(dirname(fileURLToPath(import.meta.url)), '..');
    const authRedirect = readFileSync(join(root, 'src/utils/authRedirect.ts'), 'utf8');
    assert.equal(authRedirect.includes('buildLegacyThirdLoginCallbackUrl'), false);
    const signinClient = readFileSync(join(root, 'src/app/(core)/auth/signin/SigninClient.tsx'), 'utf8');
    assert.equal(signinClient.includes('buildLegacyThirdLoginCallbackUrl'), false);
    const signinPage = readFileSync(join(root, 'src/app/(core)/auth/signin/page.tsx'), 'utf8');
    assert.equal(signinPage.includes('buildLegacyThirdLoginCallbackUrl'), false);
  });

  console.log('All auth callback URL tests passed.');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
