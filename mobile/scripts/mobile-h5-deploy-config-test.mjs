import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const projectRoot = new URL('../', import.meta.url);

async function readProjectFile(path) {
  return readFile(new URL(path, projectRoot), 'utf8');
}

async function loadApiEndpointNormalizer() {
  const source = await readProjectFile('src/api/request.ts');
  const sourceFile = ts.createSourceFile(
    'request.ts',
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  const declaration = sourceFile.statements.find(
    (node) => ts.isFunctionDeclaration(node) && node.name?.text === 'normalizeApiEndpoint',
  );

  assert.ok(declaration, 'normalizeApiEndpoint must be declared in request.ts');

  const moduleSource = ts.transpileModule(
    `${declaration.getText(sourceFile)}\nexport { normalizeApiEndpoint };`,
    { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } },
  ).outputText;
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(moduleSource).toString('base64')}`;

  return (await import(moduleUrl)).normalizeApiEndpoint;
}

test('API endpoints are normalized before reaching the H5 Nginx proxy', async () => {
  const normalizeApiEndpoint = await loadApiEndpointNormalizer();

  assert.equal(normalizeApiEndpoint('core/api/get_domain_list'), '/core/api/get_domain_list/');
  assert.equal(normalizeApiEndpoint('/core/api/login/'), '/core/api/login/');
  assert.equal(
    normalizeApiEndpoint('/opspilot/bot_mgmt/chat_application?page=1'),
    '/opspilot/bot_mgmt/chat_application/?page=1',
  );
  assert.equal(
    normalizeApiEndpoint('/core/api/get_domain_list/', { trailingSlash: false }),
    '/core/api/get_domain_list',
  );
  assert.equal(
    normalizeApiEndpoint('/core/api/login/?next=/conversation'),
    '/core/api/login/?next=/conversation',
  );
  assert.equal(
    normalizeApiEndpoint('/core/api/login/?next=/conversation', { trailingSlash: false }),
    '/core/api/login?next=/conversation',
  );
});

test('API endpoint normalization stays inside the request module', async () => {
  const requestSource = await readProjectFile('src/api/request.ts');

  assert.match(requestSource, /function normalizeApiEndpoint/);
  assert.doesNotMatch(requestSource, /from ['"]\.\/apiPath/);
  await assert.rejects(readProjectFile('src/api/apiPath.mjs'), { code: 'ENOENT' });
});

test('mobile package does not force package-wide ESM semantics', async () => {
  const packageJson = JSON.parse(await readProjectFile('package.json'));

  assert.equal(packageJson.type, undefined);
});

test('H5 image verification performs a real Docker build and Nginx config test', async () => {
  const packageJson = JSON.parse(await readProjectFile('package.json'));
  const imageTestScript = await readProjectFile('scripts/mobile-h5-image-test.mjs');

  assert.equal(packageJson.scripts['test:h5-image'], 'node scripts/mobile-h5-image-test.mjs');
  assert.match(imageTestScript, /'build'/);
  assert.match(imageTestScript, /'--no-cache'/);
  assert.match(imageTestScript, /'nginx',\s*'-t'/);
  assert.match(imageTestScript, /'--network-alias',\s*'bklite-server'/);
  assert.match(imageTestScript, /'--network-alias',\s*'bklite-web'/);
  assert.match(imageTestScript, /api\/proxy\/core\/api\/echo/);
  assert.match(imageTestScript, /api\/auth\/session/);
  assert.match(imageTestScript, /next-auth\.session-token=test-session/);
  assert.match(imageTestScript, /Set-Cookie/);
  assert.match(imageTestScript, /forwardedProto: 'https'/);
});

test('Dockerfile.h5 builds the H5 export and serves it with Nginx', async () => {
  const dockerfile = await readProjectFile('Dockerfile.h5');
  const packageJson = JSON.parse(await readProjectFile('package.json'));

  assert.match(dockerfile, /FROM node:24-alpine AS builder/);
  assert.match(dockerfile, /ARG NEXUS_NODEJS_REPOSITY/);
  assert.match(dockerfile, /npm install -g pnpm@9\.15\.4/);
  assert.match(
    dockerfile,
    /RUN pnpm run test:h5-deploy\s+RUN pnpm run lint\s+RUN pnpm run type-check\s+RUN pnpm run build:h5/,
  );
  assert.equal(packageJson.devDependencies['@next/env'], packageJson.dependencies.next);
  assert.match(dockerfile, /FROM nginx:1\.30\.4-alpine AS runtime/);
  assert.match(
    dockerfile,
    /COPY --from=builder \/app\/out \/usr\/share\/nginx\/html\/mobile\/h5/,
  );
  assert.match(dockerfile, /COPY nginx\.h5\.conf \/etc\/nginx\/nginx\.conf/);
});

test('nginx.h5.conf serves exported routes and proxies API requests', async () => {
  const nginxConfig = await readProjectFile('nginx.h5.conf');
  const nextConfig = await readProjectFile('next.config.ts');

  assert.match(
    nginxConfig,
    /location = \/healthz\s*{[\s\S]*?default_type text\/plain;/,
  );
  assert.match(nginxConfig, /location = \/\s*{[\s\S]*?return 302 \/mobile\/h5\//);
  assert.doesNotMatch(nginxConfig, /add_header Content-Type/);
  assert.match(nginxConfig, /location \^~ \/mobile\/h5\//);
  assert.match(nginxConfig, /absolute_redirect off;/);
  assert.match(
    nginxConfig,
    /map \$http_x_forwarded_proto \$proxy_x_forwarded_proto\s*{[\s\S]*?default \$http_x_forwarded_proto;[\s\S]*?'' \$scheme;/,
  );
  assert.match(
    nginxConfig,
    /rewrite \^\(\/mobile\/h5\/\.\+\)\/\$ \$1 permanent/,
  );
  assert.match(
    nginxConfig,
    /try_files \$uri \$uri\.html \/mobile\/h5\/index\.html/,
  );
  assert.doesNotMatch(nginxConfig, /try_files[^;]*\$uri\//);
  assert.doesNotMatch(nginxConfig, /expires 1y/);
  assert.match(nginxConfig, /Cache-Control "public, max-age=31536000, immutable"/);
  assert.match(nginxConfig, /location \/api\/proxy\//);
  assert.match(
    nginxConfig,
    /proxy_pass http:\/\/bklite-server:8000\/api\/v1\//,
  );
  assert.match(nginxConfig, /proxy_buffering off/);
  assert.match(nginxConfig, /proxy_set_header X-Forwarded-Proto \$proxy_x_forwarded_proto/);
  assert.match(nginxConfig, /proxy_read_timeout 300s/);
  assert.match(nginxConfig, /proxy_send_timeout 300s/);
  assert.match(nginxConfig, /location \/api\/auth\//);
  assert.match(
    nginxConfig,
    /proxy_pass http:\/\/bklite-web:3000\/api\/auth\//,
  );
  assert.match(nginxConfig, /proxy_set_header Cookie \$http_cookie/);
  assert.match(
    nextConfig,
    /source: '\/api\/auth\/:path\*'[\s\S]*destination: `\$\{devAuthProxyTarget\}\/api\/auth\/:path\*`/,
  );
  assert.match(
    nextConfig,
    /process\.env\.BK_SERVER_DEV_URL \?\? DEFAULT_DEV_SERVER_URL/,
  );
});

test('.dockerignore excludes local and generated build artifacts', async () => {
  const dockerignore = await readProjectFile('.dockerignore');

  for (const ignoredPath of ['node_modules', '.next', 'out', 'src-tauri/target', '.local-nginx']) {
    assert.match(dockerignore, new RegExp(`^${ignoredPath.replace('.', '\\.')}$`, 'm'));
  }
});
