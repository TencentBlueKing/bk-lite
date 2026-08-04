import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createLatestRequestGuard } from '../src/app/system-manager/utils/authSourceUtils';

const webRoot = path.resolve(import.meta.dirname, '..');
const read = (relativePath: string) => fs.readFileSync(path.join(webRoot, relativePath), 'utf8');
const getValue = (object: Record<string, any>, key: string) => key.split('.').reduce((value, segment) => value?.[segment], object);

const localeKeys = [
  'system.security.targetType', 'system.security.targetId', 'system.security.scenario',
  'system.security.modelObject', 'system.security.operatorObject', 'system.security.beforeAfter',
  'system.security.authSourceBkLite', 'system.security.authSourceBlueking', 'system.security.authSourceUrl',
  'system.security.authSourceWechatDescription', 'system.security.authSourceBkLiteDescription',
  'system.security.authSourceBluekingDescription', 'system.security.exportSheetName',
  'system.security.exportExcel', 'system.security.exportCsv', 'system.menu.nameMaxLength',
];

for (const locale of ['en', 'zh']) {
  const dictionary = JSON.parse(read(`src/app/system-manager/locales/${locale}.json`));
  for (const key of localeKeys) assert.equal(typeof getValue(dictionary, key), 'string', `${locale} dictionary is missing ${key}`);
}

const operationLogs = read('src/app/system-manager/components/security/operationLogs.tsx');
assert.doesNotMatch(operationLogs, /t\([^\n]+\)\s*\|\|/, 'operation log labels must not use translation fallbacks');

const authSourceTypes = read('src/app/system-manager/constants/authSources.ts');
assert.match(authSourceTypes, /bk_login:\s*\{[\s\S]*authSourceBluekingDescription/, 'BK Login source type must have a localized BlueKing description');

const authSourcesPage = read('src/app/system-manager/(pages)/user/auth-sources/page.tsx');
assert.match(authSourcesPage, /useEffect\(\(\) => \{\s*fetchAuthSources\(\);\s*fetchRoleInfo\(\);\s*\}, \[t\]\);/, 'auth-source data must refresh when the active translation function changes');
assert.match(authSourcesPage, /import \{ enhanceAuthSourcesList, createLatestRequestGuard \} from ['"]@\/app\/system-manager\/utils\/authSourceUtils['"];/, 'the page must import the request guard from authSourceUtils');
assert.doesNotMatch(authSourcesPage, /authSourceRequestGuard\.mjs/, 'the page must not import a standalone request-guard module');
assert.match(authSourcesPage, /useRef\(createLatestRequestGuard\(\)\)/, 'the page must construct one request guard instance');
assert.match(authSourcesPage, /authSourceRequestGuard\.current\.begin\('authSources'\)/, 'auth-source loading must begin a guarded request');
assert.match(authSourcesPage, /authSourceRequestGuard\.current\.begin\('roleInfo'\)/, 'role loading must begin a guarded request');
assert.match(authSourcesPage, /authSourceRequestGuard\.current\.isCurrent\('roleInfo', requestId\)/, 'role loading must reject stale responses before rendering translated role labels');

const forbiddenLiterals: Record<string, string[]> = {
  'src/app/system-manager/components/security/authSourceFormConfig.tsx': ['BK-Lite认证源', '蓝鲸认证源', '认证URL', '请输入认证URL'],
  'src/app/system-manager/constants/authSources.ts': ['支持微信平台扫码登录', '支持BK-Lite认证源', '支持蓝鲸平台认证源'],
  'src/app/system-manager/components/security/loginLogs.tsx': ["addWorksheet('Login Logs')", 'Excel (.xlsx)', 'CSV (.csv)'],
  'src/app/system-manager/(pages)/application/manage/menu/page.tsx': ['Max length 100'],
};
for (const [relativePath, literals] of Object.entries(forbiddenLiterals)) {
  const source = read(relativePath);
  for (const literal of literals) assert.ok(!source.includes(literal), `${relativePath} still contains UI copy: ${literal}`);
}

const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((completion) => { resolve = completion; });
  return { promise, resolve };
};

const verifyRequestOrdering = async () => {
const requestGuard = createLatestRequestGuard();
const zhResponse = deferred<void>();
const enResponse = deferred<void>();
let renderedDescription = '';
const loadAuthSourceDescription = async (locale: 'zh' | 'en', response: ReturnType<typeof deferred<void>>) => {
  const requestId = requestGuard.begin('authSources');
  await response.promise;
  if (requestGuard.isCurrent('authSources', requestId)) renderedDescription = locale === 'en' ? 'Supports the BlueKing platform authentication source' : '支持蓝鲸平台认证源';
};
const zhLoad = loadAuthSourceDescription('zh', zhResponse);
const enLoad = loadAuthSourceDescription('en', enResponse);
enResponse.resolve(); await enLoad; zhResponse.resolve(); await zhLoad;
assert.equal(renderedDescription, 'Supports the BlueKing platform authentication source', 'a stale zh response must not overwrite the latest en auth-source description');

const zhRolesResponse = deferred<void>();
const enRolesResponse = deferred<void>();
let renderedExternalAppLabel = '';
const loadExternalAppLabel = async (locale: 'zh' | 'en', response: ReturnType<typeof deferred<void>>) => {
  const requestId = requestGuard.begin('roleInfo');
  await response.promise;
  if (requestGuard.isCurrent('roleInfo', requestId)) renderedExternalAppLabel = locale === 'en' ? 'External App' : '外部应用';
};
const zhRolesLoad = loadExternalAppLabel('zh', zhRolesResponse);
const enRolesLoad = loadExternalAppLabel('en', enRolesResponse);
enRolesResponse.resolve(); await enRolesLoad; zhRolesResponse.resolve(); await zhRolesLoad;
assert.equal(renderedExternalAppLabel, 'External App', 'a stale zh role response must not overwrite the latest external-app label');
};

verifyRequestOrdering().then(() => console.log('system-manager Issue #4465 i18n contract passed'));
