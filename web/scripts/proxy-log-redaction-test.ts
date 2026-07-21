import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

type ProxyTargetModule = typeof import('../src/app/(core)/api/proxy/[...path]/proxyTarget');

async function main() {
  const moduleUrl = pathToFileURL(
    path.resolve(process.cwd(), 'src/app/(core)/api/proxy/[...path]/proxyTarget.ts'),
  );
  const { buildProxyTargets } = await import(moduleUrl.href) as ProxyTargetModule;

  const sensitiveSearch = '?poll_token=poll-secret&token=api-secret&code=oauth-code&state=oauth-state';
  const sensitiveTargets = buildProxyTargets(
    'https://api.example.com/api/v1',
    '/core/api/login_auth_requests/request-id/status/',
    sensitiveSearch,
  );

  assert.equal(
    sensitiveTargets.targetUrl,
    `https://api.example.com/api/v1/core/api/login_auth_requests/request-id/status/${sensitiveSearch}`,
    'the forwarded request must retain its complete query string',
  );
  assert.equal(
    sensitiveTargets.logTarget,
    'https://api.example.com/api/v1/core/api/login_auth_requests/request-id/status/',
    'the log target must contain only the destination origin and path',
  );
  for (const secret of ['poll-secret', 'api-secret', 'oauth-code', 'oauth-state']) {
    assert.equal(sensitiveTargets.logTarget.includes(secret), false, `${secret} must not enter proxy logs`);
  }

  assert.deepEqual(
    buildProxyTargets('https://api.example.com/api/v1', '/monitor/api/query/', ''),
    {
      targetUrl: 'https://api.example.com/api/v1/monitor/api/query/',
      logTarget: 'https://api.example.com/api/v1/monitor/api/query/',
    },
    'requests without query parameters must keep their existing target representation',
  );

  const routeSource = readFileSync(
    path.resolve(process.cwd(), 'src/app/(core)/api/proxy/[...path]/route.ts'),
    'utf8',
  );
  assert.match(
    routeSource,
    /const \{targetUrl, logTarget\} = buildProxyTargets\(TARGET_SERVER, targetPath, req\.nextUrl\.search\);/,
    'the proxy route must derive forwarding and logging targets together',
  );
  assert.match(routeSource, /fetch\(targetUrl, fetchOptions\)/, 'fetch must keep using the full target URL');
  assert.match(
    routeSource,
    /\[PROXY\] Forwarding Request: \$\{req\.method\} \$\{logTarget\}/,
    'forwarding logs must use the query-free target',
  );
  assert.match(
    routeSource,
    /\[PROXY\] Response Status: \$\{proxyResponse\.status\} from \$\{logTarget\}/,
    'response logs must use the query-free target',
  );
  assert.match(
    routeSource,
    /\[PROXY ERROR\] Request timeout: \$\{logTarget\}/,
    'timeout logs must use the query-free target',
  );

  const proxyLogLines = routeSource.split('\n').filter((line) => line.includes('[PROXY'));
  assert.equal(
    proxyLogLines.some((line) => line.includes('${targetUrl}')),
    false,
    'no proxy log statement may interpolate the full forwarding URL',
  );

  console.log('proxy log redaction tests passed');
}

void main();
