import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (path: string) => readFileSync(join(webRoot, path), 'utf8');

const api = read('src/app/apm/api/index.ts');
const policies = read('src/app/apm/policies/page.tsx');
const events = read('src/app/apm/events/page.tsx');
const types = read('src/app/apm/types.ts');

assert.match(types, /delivery_mode:\s*ApmNotificationDeliveryMode/, '渠道必须公开投递模式');
assert.match(types, /recipient_mode:\s*ApmNotificationRecipientMode/, '渠道必须公开接收人模式');
assert.match(api, /\/apm\/notification-deliveries\/\$\{deliveryId\}\/retry\//, '人工重投必须调用真实 API');
assert.match(api, /\/apm\/notification-recipients\//, '系统用户多选必须调用组织内公开接收人目录');
assert.match(policies, /Form\.List name="notification_targets"/, '策略表单必须支持逐渠道配置');
assert.match(policies, /recipientMode === 'none'/, '表单必须服从渠道接收人能力');
assert.match(policies, /recipientMode === 'system_user' \? 'multiple' : 'tags'/, '系统用户必须使用多选，自由接收人才使用标签输入');
assert.match(policies, /\/system-manager\/channel/, '渠道为空或不可用时必须给出配置入口');
assert.doesNotMatch(policies, /发送到告警中心/, '策略页不得保留 NATS 专属开关');
assert.match(events, /notification_deliveries/, '事件页必须呈现投递状态');
assert.match(events, /retryNotificationDelivery/, '事件页必须支持终止失败人工重投');

for (const source of [policies, events]) {
  assert.doesNotMatch(source, /(?:stories|fixtures?)\//i, 'APM 通知生产页面不得导入 Story/fixture');
}

console.log('APM notification closure checks passed');
