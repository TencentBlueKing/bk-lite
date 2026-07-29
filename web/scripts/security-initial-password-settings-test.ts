import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const read = (path: string) => readFileSync(resolve(root, path), 'utf8');

const page = read('src/app/system-manager/(pages)/user/security-settings/page.tsx');
const settings = read('src/app/system-manager/components/security/authSettings.tsx');
const api = read('src/app/system-manager/api/security/index.ts');
const zh = read('src/app/system-manager/locales/zh.json');
const en = read('src/app/system-manager/locales/en.json');

assert.match(page, /initialPasswordEnabled/);
assert.match(page, /initialPasswordRequired/);
assert.match(page, /initialPasswordEditing/);
assert.match(page, /userCreateInitialPassword/);
assert.match(settings, /initialPasswordConfigured/);
assert.match(settings, /Input\.Password/);
assert.match(settings, /newUserInitialPassword/);
assert.match(settings, /changeInitialPassword/);
assert.ok(
  settings.indexOf("newUserInitialPassword") > settings.indexOf("lockDuration"),
  '初始密码小节应在完整密码规则之后',
);
assert.match(api, /user_create_initial_password_enabled/);
assert.match(api, /user_create_initial_password/);
assert.match(zh, /新建本地用户初始密码/);
assert.match(zh, /请通过安全渠道将初始密码告知用户/);
assert.match(en, /New Local User Initial Password/);
