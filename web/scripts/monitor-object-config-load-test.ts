import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  applyObjectConfigLoadReject,
  applyObjectConfigLoadSuccess,
  canOpenObjectConfigForm,
  createObjectConfigLoadState,
  retryObjectConfigLoad,
  switchObjectConfigLoad,
} from '../src/app/monitor/hooks/integration/objectConfigLoad.ts';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const hookSource = readFileSync(
  join(webRoot, 'src/app/monitor/hooks/integration/index.tsx'),
  'utf8'
);
const getObjectConfigSource = readFileSync(
  join(webRoot, 'src/app/monitor/hooks/integration/common/getObjectConfig.ts'),
  'utf8'
);
const configureSource = readFileSync(
  join(
    webRoot,
    'src/app/monitor/(pages)/integration/list/detail/configure/page.tsx'
  ),
  'utf8'
);

const cached = createObjectConfigLoadState({
  objectName: 'Mysql',
  cached: true,
});
assert.equal(cached.status, 'ready', '缓存命中必须直接 ready');
assert.equal(canOpenObjectConfigForm(cached), true);

const waiting = createObjectConfigLoadState({ objectName: 'Mysql' });
assert.equal(waiting.status, 'waiting');
assert.equal(canOpenObjectConfigForm(waiting), false);

const rejected = applyObjectConfigLoadReject(waiting, waiting.generation);
assert.equal(rejected.status, 'error', '拒绝后必须进入 error，不能一直 waiting');
assert.equal(
  canOpenObjectConfigForm(rejected),
  false,
  '失败不得变成空配置 ready 而开放表单'
);

const retried = retryObjectConfigLoad(rejected);
assert.equal(retried.status, 'waiting');
assert.equal(retried.generation, rejected.generation + 1);

const recovered = applyObjectConfigLoadSuccess(retried, retried.generation);
assert.equal(recovered.status, 'ready', 'retry 后成功必须进入 ready');
assert.equal(canOpenObjectConfigForm(recovered), true);

const switched = switchObjectConfigLoad(waiting, { objectName: 'Redis' });
const staleSuccess = applyObjectConfigLoadSuccess(switched, waiting.generation);
const staleReject = applyObjectConfigLoadReject(switched, waiting.generation);
assert.equal(staleSuccess.status, 'waiting', '迟到成功必须丢弃');
assert.equal(staleSuccess.generation, switched.generation);
assert.equal(staleReject.status, 'waiting', '迟到拒绝必须丢弃');
assert.equal(staleReject.generation, switched.generation);

assert.match(hookSource, /from '\.\/objectConfigLoad'/);
assert.match(hookSource, /applyObjectConfigLoadReject/);
assert.match(hookSource, /retryObjectConfigLoad|retryNonce|retry\s*=/);
assert.match(getObjectConfigSource, /\berror\b/);
assert.match(getObjectConfigSource, /\bretry\b/);
assert.match(configureSource, /t\('common\.loadFailed'\)/);
assert.match(configureSource, /t\('common\.retry'\)/);
assert.match(configureSource, /objectConfigError/);
assert.match(
  configureSource,
  /if \(templateType !== 'api' && objectConfigError\) \{[\s\S]*?<Alert[\s\S]*?t\('common\.loadFailed'\)[\s\S]*?t\('common\.retry'\)[\s\S]*?if \(templateType !== 'api' && !objectConfigReady\)/,
  '失败时先 Alert 重试，不得在 error 时开放采集表单'
);

console.log('monitor object config load passed');
