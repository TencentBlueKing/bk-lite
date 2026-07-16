import assert from 'node:assert/strict';
import fs from 'node:fs';

const statuses = [
  'waiting_sync',
  'running',
  'submitted',
  'success',
  'partial_success',
  'blocked',
  'failed',
  'timeout',
] as const;

const componentSource = fs.readFileSync(
  'src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/nodeMgmtSyncDetail.tsx',
  'utf8'
);
assert.match(componentSource, /Record<NodeMgmtSyncStatus, BadgeStatus>/, '运行状态 Badge 映射必须穷尽');
for (const status of statuses) {
  assert.match(componentSource, new RegExp(`\\b${status}:`), `缺少 ${status} 状态映射`);
}
assert.match(componentSource, /submitted:\s*'processing'/, 'submitted 不得显示为 success');
assert.match(componentSource, /NODE_QUERY_FAILED[\s\S]*nodeQueryFailed/, '查询失败必须使用稳定错误码映射');
assert.match(componentSource, /NO_ACCESS_POINT[\s\S]*noAccessPoint/, '无接入点必须使用稳定错误码映射');
assert.match(componentSource, /reason\.unknown/, '未知错误码必须使用脱敏 fallback');
assert.match(componentSource, /empty\.noNodes/, '真正空源必须与请求失败分流');
assert.match(componentSource, /disabled=\{saving\}/, '保存期间两个开关都必须禁用');
assert.match(componentSource, /setTask\(response\)[\s\S]*await fetchData/, 'PUT 返回后必须采用服务端状态并重新拉取收敛结果');
assert.match(componentSource, /<Button loading=\{loading\}/, '刷新按钮必须显示加载反馈');
assert.match(componentSource, /refreshSuccess/, '刷新成功必须给出反馈');
assert.match(componentSource, /useEffect\([\s\S]*if \(!open\)[\s\S]*fetchData\(\)/, '首次打开和关闭后重开都必须重新拉取');
assert.doesNotMatch(componentSource, /auto_collect_enabled\s*=\s*false/, '关闭自动同步不得伪造后端自动采集状态');
assert.doesNotMatch(componentSource, /disabled=\{!task\?\.auto_sync_enabled\}/, '自动采集开关必须能表达 waiting_sync');
assert.doesNotMatch(componentSource, /syncRun\?\.error_message|health\?\.message/, '不得直接展示后端原始错误文本');

const typeSource = fs.readFileSync('src/app/cmdb/types/autoDiscovery.ts', 'utf8');
for (const field of ['schedule_status', 'node_config_status', 'reason_code', 'next_retry_at', 'error_code']) {
  assert.match(typeSource, new RegExp(`\\b${field}\\??:`), `类型缺少后端字段 ${field}`);
}

for (const locale of ['zh', 'en']) {
  const messages = JSON.parse(fs.readFileSync(`src/app/cmdb/locales/${locale}.json`, 'utf8'));
  const nodeMgmtSync = messages.Collection.nodeMgmtSync;
  assert.ok(nodeMgmtSync.health, `${locale}: 缺少 health 文案`);
  assert.ok(nodeMgmtSync.status?.submitted, `${locale}: submitted 不得显示为 success`);
  assert.ok(nodeMgmtSync.empty?.noNodes, `${locale}: 缺少真实空节点文案`);
  assert.ok(nodeMgmtSync.empty?.queryFailed, `${locale}: 缺少查询失败文案`);
  assert.ok(nodeMgmtSync.empty?.noAccessPoint, `${locale}: 缺少无接入点文案`);
  assert.ok(nodeMgmtSync.reason?.unknown, `${locale}: 缺少未知错误码脱敏 fallback`);
}

console.log('cmdb-node-mgmt-sync-health test passed');
