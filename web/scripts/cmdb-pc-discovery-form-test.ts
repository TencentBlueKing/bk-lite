/**
 * PC 发现配置采集表单合同测试。
 *
 * 锁定：
 * - 纯函数：getPCCredentialShape / getPCDefaults / buildPCSubmitPayload / buildPCFormValues；
 * - 提交负载符合 server pc_collect_policy 契约（os_type、winrm_scheme/transport/cert_validation、
 *   macOS 密码 XOR 私钥、编辑切换认证方式显式清空另一种秘密）；
 * - 掩码秘密（******）绝不出现在提交负载；
 * - 静态接线：page.tsx 以 model_id === 'pc' 路由 PCTask；PCTask 只含一个 BaseTaskForm；
 *   CredentialPoolEditor 支持 winrm/macos_ssh；collect API 暴露 pcTestConnection；
 *   BaseTaskForm 提供 afterTaskName 注入点；中英文案包含 PCTask。
 *
 * Run: pnpm exec tsx scripts/cmdb-pc-discovery-form-test.ts
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  buildPCFormValues,
  buildPCSubmitPayload,
  getPCCredentialShape,
  getPCDefaults,
} from '../src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/utils/pcTask';

const MASK = '******';

// ------------------------------------------------------------ 凭据形态
assert.equal(getPCCredentialShape('windows'), 'winrm');
assert.equal(getPCCredentialShape('macos'), 'macos_ssh');

// ------------------------------------------------------------ 默认值
assert.deepEqual(getPCDefaults('windows'), {
  osType: 'windows',
  timeout: 120,
  cleanupStrategy: 'immediately',
  credentialPool: [{ port: 5986, scheme: 'https', transport: 'ntlm', certValidation: false }],
});
assert.deepEqual(getPCDefaults('macos'), {
  osType: 'macos',
  timeout: 120,
  cleanupStrategy: 'immediately',
  credentialPool: [{ port: 22, authType: 'password' }],
});

// ------------------------------------------------------------ Windows 提交负载
const windowsPayload = buildPCSubmitPayload({
  osType: 'windows',
  credentialPool: [
    { username: ' ACME\\alice ', password: 'secret', port: 5986, scheme: 'https', transport: 'ntlm', certValidation: false },
  ],
});
assert.equal(windowsPayload.params.os_type, 'windows');
assert.equal(windowsPayload.params.winrm_scheme, 'https');
assert.equal(windowsPayload.params.winrm_transport, 'ntlm');
assert.equal(windowsPayload.params.winrm_cert_validation, false);
assert.deepEqual(windowsPayload.credential, [
  { username: 'ACME\\alice', password: 'secret', port: 5986 },
]);

// 显式 HTTP/5985（安全提示由 server 写入 security_warning，前端只透传 scheme/port）
const httpPayload = buildPCSubmitPayload({
  osType: 'windows',
  credentialPool: [
    { username: 'alice', password: 'secret', port: 5985, scheme: 'http', transport: 'ntlm', certValidation: false },
  ],
});
assert.equal(httpPayload.params.winrm_scheme, 'http');
assert.equal(httpPayload.credential[0].port, 5985);

// 编辑回填的掩码密码不下发（server 按 credential_id 合并保留原秘密）
const maskedPayload = buildPCSubmitPayload({
  osType: 'windows',
  credentialPool: [
    { credential_id: 'cred-1', username: 'alice', password: MASK, port: 5986, scheme: 'https', transport: 'ntlm', certValidation: true },
  ],
});
assert.equal(maskedPayload.credential[0].credential_id, 'cred-1');
assert.equal('password' in maskedPayload.credential[0], false);
assert.equal(maskedPayload.params.winrm_cert_validation, true);
assert.equal(JSON.stringify(maskedPayload).includes(MASK), false);

// ------------------------------------------------------------ macOS 提交负载
const macosPasswordPayload = buildPCSubmitPayload({
  osType: 'macos',
  credentialPool: [{ username: 'admin', password: 'secret', port: 22, authType: 'password' }],
});
assert.deepEqual(macosPasswordPayload.params, { os_type: 'macos' });
assert.deepEqual(macosPasswordPayload.credential, [
  { username: 'admin', password: 'secret', port: 22 },
]);

const macosKeyPayload = buildPCSubmitPayload({
  osType: 'macos',
  credentialPool: [
    {
      username: 'admin',
      port: 22,
      authType: 'privateKey',
      private_key: '-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----',
      passphrase: 'pp',
    },
  ],
});
assert.equal(macosKeyPayload.credential[0].private_key.includes('BEGIN'), true);
assert.equal(macosKeyPayload.credential[0].passphrase, 'pp');
assert.equal('password' in macosKeyPayload.credential[0], false);

// 编辑切换认证方式：密码 → 私钥，显式清空旧密码（server XOR 校验要求）
const switchToKey = buildPCSubmitPayload({
  osType: 'macos',
  credentialPool: [
    { credential_id: 'cred-2', username: 'admin', port: 22, authType: 'privateKey', password: MASK, private_key: 'PEM-DATA', passphrase: '' },
  ],
});
assert.equal(switchToKey.credential[0].password, '');
assert.equal(switchToKey.credential[0].private_key, 'PEM-DATA');

// 编辑切换认证方式：私钥 → 密码，显式清空旧私钥与密码短语
const switchToPassword = buildPCSubmitPayload({
  osType: 'macos',
  credentialPool: [
    { credential_id: 'cred-3', username: 'admin', port: 22, authType: 'password', password: 'new-secret', private_key: MASK, passphrase: MASK },
  ],
});
assert.equal(switchToPassword.credential[0].password, 'new-secret');
assert.equal(switchToPassword.credential[0].private_key, '');
assert.equal(switchToPassword.credential[0].passphrase, '');

// 编辑不动私钥：掩码私钥/密码短语均不下发
const keepKey = buildPCSubmitPayload({
  osType: 'macos',
  credentialPool: [
    { credential_id: 'cred-4', username: 'admin', port: 22, authType: 'privateKey', private_key: MASK, passphrase: MASK },
  ],
});
assert.equal('private_key' in keepKey.credential[0], false);
assert.equal('passphrase' in keepKey.credential[0], false);
assert.equal(JSON.stringify(keepKey).includes(MASK), false);

// ------------------------------------------------------------ 编辑/复制回填
const taskDetail = {
  name: 'pc-discovery',
  team: [1, 2],
  access_point: [{ id: 7 }],
  params: { os_type: 'macos', winrm_scheme: 'https', winrm_cert_validation: false },
  credential: [{ credential_id: 'cred-9', username: 'admin', private_key: MASK, passphrase: MASK, port: 22 }],
};

const editValues = buildPCFormValues(taskDetail, false);
assert.equal(editValues.osType, 'macos');
assert.equal(editValues.taskName, 'pc-discovery');
assert.deepEqual(editValues.organization, [1, 2]);
assert.equal(editValues.accessPointId, 7);
assert.equal(editValues.credentialPool[0].authType, 'privateKey');
assert.equal(editValues.credentialPool[0].private_key, MASK);

const copyValues = buildPCFormValues(taskDetail, true);
assert.equal(copyValues.taskName, '');
assert.equal(copyValues.osType, 'macos', '复制任务允许重新选择 OS，但默认沿用原 OS');
assert.equal(copyValues.credentialPool[0].private_key, '', '复制任务清空所有秘密值');
assert.equal(copyValues.credentialPool[0].passphrase, '');

const windowsDetail = {
  name: 'win-pc',
  team: [3],
  access_point: [{ id: 8 }],
  params: { os_type: 'windows', winrm_scheme: 'http', winrm_cert_validation: true },
  credential: [{ credential_id: 'cred-10', username: 'alice', password: MASK, port: 5985 }],
};
const windowsEditValues = buildPCFormValues(windowsDetail, false);
assert.equal(windowsEditValues.credentialPool[0].scheme, 'http');
assert.equal(windowsEditValues.credentialPool[0].certValidation, true);
assert.equal(windowsEditValues.credentialPool[0].password, MASK);

// ------------------------------------------------------------ 静态接线断言
const readSrc = (path: string) => readFileSync(resolve(__dirname, '..', path), 'utf-8');

const pageSource = readSrc('src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/page.tsx');
assert.ok(pageSource.includes("import PCTask from './components/pcTask'"), 'page.tsx 应导入 PCTask');
assert.ok(
  pageSource.includes("currentPlugin.model_id === 'pc'"),
  'page.tsx 应在通用 taskMap 前以 model_id === pc 路由'
);
assert.ok(
  pageSource.indexOf("currentPlugin.model_id === 'pc'") < pageSource.indexOf('const taskMap'),
  'pc 路由必须先于通用 taskMap 兜底'
);

const pcTaskSource = readSrc('src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/pcTask.tsx');
assert.equal(pcTaskSource.match(/<BaseTaskForm/g)?.length, 1, 'PCTask 应包含且只包含一个 BaseTaskForm');
assert.ok(!pcTaskSource.includes('<Drawer'), 'PCTask 不得另造抽屉');
assert.ok(pcTaskSource.includes('afterTaskName'), 'PCTask 应把 OS 选择注入任务名称之后');
assert.ok(pcTaskSource.includes('pcTestConnection'), 'PCTask 测试按钮应调用连接测试 API');

const editorSource = readSrc('src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialPoolEditor.tsx');
assert.ok(editorSource.includes("'winrm'"), 'CredentialPoolEditor 应支持 winrm 形态');
assert.ok(editorSource.includes("'macos_ssh'"), 'CredentialPoolEditor 应支持 macos_ssh 形态');

const baseTaskSource = readSrc('src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/baseTask.tsx');
assert.ok(baseTaskSource.includes('afterTaskName'), 'BaseTaskForm 应提供 afterTaskName 注入点');

const apiSource = readSrc('src/app/cmdb/api/collect.ts');
assert.ok(apiSource.includes('pc_test_connection'), 'collect API 应暴露 PC 连接测试端点');

const zhLocale = JSON.parse(readSrc('src/app/cmdb/locales/zh.json'));
const enLocale = JSON.parse(readSrc('src/app/cmdb/locales/en.json'));
assert.ok(zhLocale.Collection?.PCTask?.osType, 'zh.json 应包含 Collection.PCTask.osType');
assert.ok(enLocale.Collection?.PCTask?.osType, 'en.json 应包含 Collection.PCTask.osType');
assert.ok(zhLocale.Collection?.PCTask?.winrmHttpWarning, 'zh.json 应包含 WinRM HTTP 安全警告文案');

console.log('cmdb-pc-discovery-form-test passed');
