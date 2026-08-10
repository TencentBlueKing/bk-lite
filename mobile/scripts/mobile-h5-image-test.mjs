#!/usr/bin/env node

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';

const image = process.env.MOBILE_H5_TEST_IMAGE || 'bklite-mobile-h5:test';
const nexusRegistry = process.env.NEXUS_NODEJS_REPOSITY || '';
const containerName = `bklite-mobile-h5-test-${process.pid}`;
const upstreamName = `bklite-mobile-h5-upstream-${process.pid}`;
const authUpstreamName = `bklite-mobile-h5-auth-upstream-${process.pid}`;
const networkName = `bklite-mobile-h5-network-${process.pid}`;

function runDocker(args, { allowFailure = false, stdio = 'inherit' } = {}) {
  const result = spawnSync('docker', args, {
    cwd: process.cwd(),
    stdio,
    shell: process.platform === 'win32',
  });

  if (result.error) {
    throw result.error;
  }

  if (!allowFailure && result.status !== 0) {
    throw new Error(`docker ${args.join(' ')} failed with exit code ${result.status ?? 1}`);
  }

  return result;
}

function waitForNginx() {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const result = runDocker(
      ['exec', containerName, 'wget', '-q', '--spider', 'http://127.0.0.1/healthz'],
      { allowFailure: true, stdio: 'ignore' },
    );

    if (result.status === 0) return;
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 250);
  }

  throw new Error('Nginx did not become ready within 5 seconds');
}

function waitForNodeServer(name, port, label) {
  const probe = `fetch('http://127.0.0.1:${port}/healthz').then(response => process.exit(response.ok ? 0 : 1)).catch(() => process.exit(1))`;

  for (let attempt = 0; attempt < 20; attempt += 1) {
    const result = runDocker(
      ['exec', name, 'node', '-e', probe],
      { allowFailure: true, stdio: 'ignore' },
    );

    if (result.status === 0) return;
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 250);
  }

  throw new Error(`${label} did not become ready within 5 seconds`);
}

const buildArgs = ['build', '--no-cache'];
if (nexusRegistry) {
  buildArgs.push('--build-arg', `NEXUS_NODEJS_REPOSITY=${nexusRegistry}`);
}
buildArgs.push('-f', 'Dockerfile.h5', '-t', image, '.');

runDocker(buildArgs);
runDocker([
  'run',
  '--rm',
  '--add-host',
  'bklite-server:127.0.0.1',
  '--add-host',
  'bklite-web:127.0.0.1',
  image,
  'nginx',
  '-t',
]);

const routeChecks = [
  ['/mobile/h5/', 'index.html'],
  ['/mobile/h5/login', 'login.html'],
  ['/mobile/h5/login/', 'login.html'],
  ['/mobile/h5/profile/', 'profile.html'],
  ['/mobile/h5/workbench/', 'workbench.html'],
  ['/mobile/h5/workbench/detail/', 'workbench/detail.html'],
];

const mockServerSource = `
const http = require('node:http');

http.createServer((request, response) => {
  let body = '';
  request.setEncoding('utf8');
  request.on('data', (chunk) => { body += chunk; });
  request.on('end', () => {
    response.writeHead(200, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({
      method: request.method,
      url: request.url,
      authorization: request.headers.authorization,
      cookie: request.headers.cookie,
      forwardedProto: request.headers['x-forwarded-proto'],
      body,
    }));
  });
}).listen(8000, '0.0.0.0');
`;

const mockAuthServerSource = `
const http = require('node:http');

http.createServer((request, response) => {
  if (request.url === '/healthz') {
    response.writeHead(200, { 'Content-Type': 'text/plain' });
    response.end('ok');
    return;
  }

  let body = '';
  request.setEncoding('utf8');
  request.on('data', (chunk) => { body += chunk; });
  request.on('end', () => {
    response.writeHead(200, {
      'Content-Type': 'application/json',
      'Set-Cookie': 'next-auth.session-token=test-session; Path=/; HttpOnly; SameSite=Lax',
    });
    response.end(JSON.stringify({
      method: request.method,
      url: request.url,
      cookie: request.headers.cookie,
      forwardedProto: request.headers['x-forwarded-proto'],
      body,
    }));
  });
}).listen(3000, '0.0.0.0');
`;

try {
  runDocker(['network', 'create', networkName]);
  runDocker([
    'run',
    '--rm',
    '--detach',
    '--name',
    upstreamName,
    '--network',
    networkName,
    '--network-alias',
    'bklite-server',
    'node:24-alpine',
    'node',
    '-e',
    mockServerSource,
  ]);
  waitForNodeServer(upstreamName, 8000, 'Mock bklite-server');

  runDocker([
    'run',
    '--rm',
    '--detach',
    '--name',
    authUpstreamName,
    '--network',
    networkName,
    '--network-alias',
    'bklite-web',
    'node:24-alpine',
    'node',
    '-e',
    mockAuthServerSource,
  ]);
  waitForNodeServer(authUpstreamName, 3000, 'Mock bklite-web');

  runDocker([
    'run',
    '--rm',
    '--detach',
    '--name',
    containerName,
    '--network',
    networkName,
    image,
  ]);
  waitForNginx();

  const redirectHeaders = runDocker(
    [
      'exec',
      containerName,
      'wget',
      '-S',
      '--spider',
      '--header',
      'X-Forwarded-Proto: https',
      'http://127.0.0.1/mobile/h5/login/',
    ],
    { stdio: 'pipe' },
  ).stderr.toString();
  assert.match(
    redirectHeaders,
    /Location: \/mobile\/h5\/login\s/im,
    'trailing-slash redirects must stay relative behind a TLS-terminating proxy',
  );

  for (const [route, exportedFile] of routeChecks) {
    const response = runDocker(
      ['exec', containerName, 'wget', '-qO-', `http://127.0.0.1${route}`],
      { stdio: 'pipe' },
    ).stdout;
    const expected = runDocker(
      [
        'exec',
        containerName,
        'cat',
        `/usr/share/nginx/html/mobile/h5/${exportedFile}`,
      ],
      { stdio: 'pipe' },
    ).stdout;

    assert.deepEqual(response, expected, `${route} did not serve ${exportedFile}`);
  }

  const requestBody = JSON.stringify({ message: 'hello' });
  const proxyResponse = runDocker(
    [
      'exec',
      containerName,
      'wget',
      '-qO-',
      '--header',
      'Authorization: Bearer test-token',
      '--header',
      'Cookie: bklite_token=test-cookie; current_team=7',
      '--header',
      'X-Forwarded-Proto: https',
      '--post-data',
      requestBody,
      'http://127.0.0.1/api/proxy/core/api/echo/?page=1',
    ],
    { stdio: 'pipe' },
  ).stdout.toString();

  assert.deepEqual(JSON.parse(proxyResponse), {
    method: 'POST',
    url: '/api/v1/core/api/echo/?page=1',
    authorization: 'Bearer test-token',
    cookie: 'bklite_token=test-cookie; current_team=7',
    forwardedProto: 'https',
    body: requestBody,
  });

  const authResponse = runDocker(
    [
      'exec',
      containerName,
      'wget',
      '-S',
      '-qO-',
      '--header',
      'Cookie: next-auth.session-token=test-session',
      '--header',
      'X-Forwarded-Proto: https',
      'http://127.0.0.1/api/auth/session',
    ],
    { stdio: 'pipe' },
  );

  assert.match(
    authResponse.stderr.toString(),
    /Set-Cookie: next-auth\.session-token=test-session; Path=\/; HttpOnly; SameSite=Lax/i,
  );
  assert.deepEqual(JSON.parse(authResponse.stdout.toString()), {
    method: 'GET',
    url: '/api/auth/session',
    cookie: 'next-auth.session-token=test-session',
    forwardedProto: 'https',
    body: '',
  });
} finally {
  runDocker(['rm', '--force', containerName], { allowFailure: true, stdio: 'ignore' });
  runDocker(['rm', '--force', upstreamName], { allowFailure: true, stdio: 'ignore' });
  runDocker(['rm', '--force', authUpstreamName], { allowFailure: true, stdio: 'ignore' });
  runDocker(['network', 'rm', networkName], { allowFailure: true, stdio: 'ignore' });
}
