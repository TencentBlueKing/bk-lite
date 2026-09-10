import * as assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const alarmDir = resolve(here, '../src/app/alarm');
const pageSource = readFileSync(
  resolve(alarmDir, '(pages)/incidents/detail/page.tsx'),
  'utf8'
);

function extractFunction(source: string, name: string): string {
  const start = source.indexOf(`const ${name}`);
  assert.ok(start >= 0, `${name} must exist on the incident detail page`);
  const nextConst = source.indexOf('\n  const ', start + 1);
  const nextExport = source.indexOf('\nexport ', start + 1);
  const end = [nextConst, nextExport].filter((idx) => idx > start).sort((a, b) => a - b)[0];
  assert.ok(end, `${name} body must be extractable`);
  return source.slice(start, end);
}

const handleLinkConfirm = extractFunction(pageSource, 'handleLinkConfirm');
const handleUnlink = extractFunction(pageSource, 'handleUnlink');

assert.doesNotMatch(
  handleLinkConfirm,
  /tableData\.map/,
  'handleLinkConfirm must not rebuild the full alert set from visible tableData'
);
assert.doesNotMatch(
  handleUnlink,
  /tableData\.map/,
  'handleUnlink must not rebuild remaining alerts from visible tableData'
);
assert.doesNotMatch(
  handleLinkConfirm,
  /modifyIncidentDetail\([\s\S]*alert:/,
  'handleLinkConfirm must not PATCH alert as a full replacement set'
);
assert.doesNotMatch(
  handleUnlink,
  /modifyIncidentDetail\([\s\S]*alert:/,
  'handleUnlink must not PATCH alert as a full replacement set'
);
assert.match(
  pageSource,
  /addAlertsToIncident,\s*\n\s*removeAlertsFromIncident/,
  'incident detail must use incremental add/remove APIs'
);
assert.match(
  handleLinkConfirm,
  /const selectedIds = collectSelectedAlertIds\(selectedKeys\);\s*\n\s*if \(!selectedIds\.length\) return;/,
  'empty link selection must not send a request'
);
assert.match(
  handleLinkConfirm,
  /addAlertsToIncident\(rowDetailId,\s*selectedIds\)/,
  'link must add only the selected alert IDs'
);
assert.match(
  handleUnlink,
  /const selectedIds = collectSelectedAlertIds\(keys \?\? selectedRowKeys\);\s*\n\s*if \(!selectedIds\.length\) return;/,
  'empty unlink selection must not send a request'
);
assert.match(
  handleUnlink,
  /removeAlertsFromIncident\(rowDetailId,\s*selectedIds\)/,
  'unlink must remove only the selected alert IDs'
);
assert.match(
  handleLinkConfirm,
  /message\.success\([\s\S]*linkAlert/,
  'successful link must keep the existing success toast'
);
assert.match(
  handleUnlink,
  /message\.success\([\s\S]*unlinkAlert/,
  'successful unlink must keep the existing success toast'
);
assert.match(
  handleLinkConfirm,
  /fetchAlarmList\(\);\s*\n\s*fetchTimeline\(\);/,
  'successful link must refresh the filtered list and timeline'
);
assert.match(
  handleUnlink,
  /fetchAlarmList\(\);\s*\n\s*fetchTimeline\(\);/,
  'successful unlink must refresh the filtered list and timeline'
);
assert.doesNotMatch(
  handleLinkConfirm.split('} catch')[1] || '',
  /fetchAlarmList|fetchTimeline|message\.success/,
  'failed link must not toast success or refresh'
);
assert.doesNotMatch(
  handleUnlink.split('} catch')[1] || '',
  /fetchAlarmList|fetchTimeline|message\.success/,
  'failed unlink must not toast success or refresh'
);
assert.match(
  pageSource,
  /modifyIncidentDetail\(rowDetailId, \{ operator:/,
  'PATCH replacement remains for other incident fields'
);
assert.match(
  pageSource,
  /<PermissionWrapper requiredPermissions=\{\['Edit'\]\}>[\s\S]*handleLink\(\)/,
  'link button must stay behind Edit permission'
);
assert.match(
  pageSource,
  /<PermissionWrapper requiredPermissions=\{\['Edit'\]\}>[\s\S]*handleUnlink\(\)/,
  'unlink button must stay behind Edit permission'
);

async function assertSelectedAlertIds() {
  const { collectSelectedAlertIds } = await import(
    '../src/app/alarm/utils/incidentAlertRelations.ts'
  );

  const visibleTableIds = [101, 202];
  const hiddenServerIds = [303];

  assert.deepEqual(collectSelectedAlertIds([]), []);
  assert.deepEqual(collectSelectedAlertIds(undefined), []);
  assert.deepEqual(collectSelectedAlertIds(null), []);

  const linkIds = collectSelectedAlertIds([404]);
  assert.deepEqual(linkIds, [404]);
  assert.equal(
    linkIds.some((id) => visibleTableIds.includes(id) || hiddenServerIds.includes(id)),
    false,
    'link payload must be selected IDs only, never a union with visible or hidden table rows'
  );

  assert.deepEqual(
    collectSelectedAlertIds([12, '34', 56n, 'x']),
    [12, 34],
    'bigint React keys must be dropped, numeric strings kept'
  );

  const unlinkIds = collectSelectedAlertIds([101]);
  assert.deepEqual(unlinkIds, [101]);
  assert.notDeepEqual(
    unlinkIds,
    visibleTableIds.filter((id) => id !== 101),
    'unlink payload must not be the remaining visible table IDs'
  );
}

assertSelectedAlertIds()
  .then(() => {
    console.log('incident detail alert link test passed');
  })
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
