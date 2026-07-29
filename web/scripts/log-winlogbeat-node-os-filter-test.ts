/**
 * Windows 事件日志节点操作系统筛选回归测试。
 *
 * 运行：`pnpm exec tsx scripts/log-winlogbeat-node-os-filter-test.ts`
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const workspaceRoot = process.cwd();
const winlogbeatConfig = fs.readFileSync(
  path.join(
    workspaceRoot,
    'src/app/log/hooks/integration/collectors/winlogbeat/winlogbeat.tsx'
  ),
  'utf8'
);
const automaticConfiguration = fs.readFileSync(
  path.join(
    workspaceRoot,
    'src/app/log/(pages)/integration/list/detail/configure/automatic.tsx'
  ),
  'utf8'
);
const integrationApi = fs.readFileSync(
  path.join(workspaceRoot, 'src/app/log/api/integration.ts'),
  'utf8'
);

assert.match(
  winlogbeatConfig,
  /nodeOperatingSystem:\s*['"]windows['"]\s+as const/,
  'Winlogbeat 必须声明只支持 Windows 节点'
);
assert.match(
  automaticConfiguration,
  /os:\s*configsInfo\.nodeOperatingSystem/,
  '自动配置页必须将采集器声明的操作系统传给节点接口'
);
assert.match(
  integrationApi,
  /os\?:\s*['"]linux['"]\s*\|\s*['"]windows['"]/,
  '节点接口类型必须接受受限的操作系统参数'
);

console.log('Windows 事件日志节点操作系统筛选测试通过');
