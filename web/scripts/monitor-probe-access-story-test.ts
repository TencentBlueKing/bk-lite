import fs from 'fs';
import path from 'path';

const repoRoot = path.resolve(process.cwd(), '..');
const storyPath = path.join(process.cwd(), 'src/stories/monitor-probe-access.stories.tsx');
const pingUiPath = path.join(
  repoRoot,
  'server/apps/monitor/support-files/plugins/Telegraf/ping/ping/UI.json'
);
const websiteUiPath = path.join(
  repoRoot,
  'server/apps/monitor/support-files/plugins/Telegraf/web/web/UI.json'
);

const readJson = (filePath: string) => JSON.parse(fs.readFileSync(filePath, 'utf8'));
const pingUi = readJson(pingUiPath);
const websiteUi = readJson(websiteUiPath);

const assert = (condition: unknown, message: string) => {
  if (!condition) {
    throw new Error(message);
  }
};

const byName = (items: any[]) =>
  Object.fromEntries(items.map((item) => [item.name, item]));

const pingForm = byName(pingUi.form_fields);
const pingColumns = byName(pingUi.table_columns);
const websiteForm = byName(websiteUi.form_fields);
const websiteColumns = byName(websiteUi.table_columns);

assert(!pingForm.ip_version, 'Ping IP version should not require manual form selection');
assert(!pingColumns.ip_version, 'Ping IP version should not require manual table selection');
assert(websiteForm.insecure_skip_verify?.type === 'switch', 'Website TLS switch should be global form config');
assert(!websiteForm.insecure_skip_verify?.visible_in, 'Website TLS switch should be visible in auto global config');
assert(!websiteColumns.insecure_skip_verify, 'Website TLS switch should not appear as a per-instance table column');

assert(fs.existsSync(storyPath), 'Monitor probe access Storybook story should exist');
const storySource = fs.readFileSync(storyPath, 'utf8');

[
  "title: 'Monitor/ProbeAccess'",
  'ProbeAccessFrame',
  'PingProbe',
  'WebsiteProbe',
  'URL（IPv4/IPv6）',
  'example.com / 192.168.1.1 / 2001:db8::1',
  '自动识别 IPv6 字面量',
  'IPv6 URL 需使用方括号格式'
].forEach((expected) => {
  assert(storySource.includes(expected), `Story should include ${expected}`);
});

console.log('monitor probe access story contract OK');
