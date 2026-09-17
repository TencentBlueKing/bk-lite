import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const page = readFileSync(
  resolve(process.cwd(), 'src/app/patch-manager/(pages)/risk-pending/page.tsx'),
  'utf8',
);
const exportAllHandler = page.match(
  /const handleExportAll = async \(\) => \{[\s\S]*?\n  \};/,
)?.[0] || '';
const exportSelectedHandler = page.match(
  /const handleExportSelected = async \(\) => \{[\s\S]*?\n  \};/,
)?.[0] || '';

assert.ok(exportAllHandler, '缺少 handleExportAll');
assert.doesNotMatch(
  exportAllHandler,
  /buildWorkbook\(riskData/,
  '导出全部不得把当前页 riskData 写入工作簿',
);
assert.match(exportAllHandler, /collectPendingRiskExportRows/);
assert.match(exportAllHandler, /noExportData/);
assert.match(exportAllHandler, /exportTruncated/);
assert.doesNotMatch(exportAllHandler, /catch\s*\{\s*\}/);
assert.doesNotMatch(page, /page_size:\s*10000/);
assert.match(page, /buildPendingRiskListParams/);
assert.match(exportSelectedHandler, /buildWorkbook\(selectedRows/);

async function main() {
  const {
    PENDING_RISK_EXPORT_MAX_ROWS,
    PENDING_RISK_EXPORT_PAGE_SIZE,
    buildPendingRiskListParams,
    collectPendingRiskExportRows,
  } = await import('../src/app/patch-manager/utils/pending-risk-export.ts');

  assert.equal(PENDING_RISK_EXPORT_PAGE_SIZE, 100);
  assert.ok(PENDING_RISK_EXPORT_MAX_ROWS > PENDING_RISK_EXPORT_PAGE_SIZE);

  const hostParams = buildPendingRiskListParams(
    'host',
    { host_name: 'web', os_type: 'win', remediation: 'unplanned', patch_name: 'ignored' },
    { page: 2, pageSize: PENDING_RISK_EXPORT_PAGE_SIZE, hostId: 7 },
  );
  assert.deepEqual(hostParams, {
    view: 'host',
    page: 2,
    page_size: 100,
    host_id: 7,
    host_name: 'web',
    os_type: 'windows',
    remediation: 'unplanned',
  });

  const patchParams = buildPendingRiskListParams(
    'patch',
    { patch_name: 'openssl', severity: 'critical', host_name: 'ignored' },
    { page: 1, pageSize: PENDING_RISK_EXPORT_PAGE_SIZE },
  );
  assert.deepEqual(patchParams, {
    view: 'patch',
    page: 1,
    page_size: 100,
    patch_name: 'openssl',
    severity: 'critical',
  });

  const allRows = Array.from({ length: 250 }, (_, index) => ({ key: `row-${index}` }));
  const requests: Array<Record<string, unknown>> = [];
  const pagedList = async (params: Record<string, unknown>) => {
    requests.push(params);
    const pageSize = Number(params.page_size);
    const currentPage = Number(params.page);
    const start = (currentPage - 1) * pageSize;
    return { count: allRows.length, results: allRows.slice(start, start + pageSize) };
  };

  const collected = await collectPendingRiskExportRows(
    pagedList,
    'host',
    { host_name: 'web', os_type: 'win', remediation: 'unplanned' },
    { hostId: 7 },
  );
  assert.equal(collected.rows.length, 250);
  assert.equal(collected.total, 250);
  assert.equal(collected.truncated, false);
  assert.equal(requests.length, 3);
  assert.deepEqual(requests.map((item) => item.page), [1, 2, 3]);
  for (const request of requests) {
    assert.equal(request.page_size, 100);
    assert.equal(request.view, 'host');
    assert.equal(request.host_name, 'web');
    assert.equal(request.os_type, 'windows');
    assert.equal(request.host_id, 7);
    assert.equal(request.remediation, 'unplanned');
  }

  requests.length = 0;
  const cappedRows = Array.from({ length: 350 }, (_, index) => ({ key: `cap-${index}` }));
  const cappedList = async (params: Record<string, unknown>) => {
    requests.push(params);
    const pageSize = Number(params.page_size);
    const currentPage = Number(params.page);
    const start = (currentPage - 1) * pageSize;
    return { count: cappedRows.length, results: cappedRows.slice(start, start + pageSize) };
  };

  const truncated = await collectPendingRiskExportRows(
    cappedList,
    'patch',
    { patch_name: 'openssl', severity: 'critical' },
    { pageSize: 100, maxRows: 200 },
  );
  assert.equal(truncated.rows.length, 200);
  assert.equal(truncated.total, 350);
  assert.equal(truncated.truncated, true);
  assert.equal(requests.length, 2);
  assert.deepEqual(requests.map((item) => item.page), [1, 2]);
  for (const request of requests) {
    assert.equal(request.page_size, 100);
    assert.equal(request.view, 'patch');
    assert.equal(request.patch_name, 'openssl');
    assert.equal(request.severity, 'critical');
  }

  console.log('待治理风险导出全部按筛选分页拉取约束通过');
}

void main();
