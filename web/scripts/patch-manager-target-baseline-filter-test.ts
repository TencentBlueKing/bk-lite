import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import {
  buildTargetFilterSearch,
  parseBaselineFilter,
} from '../src/app/patch-manager/(pages)/target/filter-state';

assert.equal(parseBaselineFilter(new URLSearchParams()), undefined, '未携带路由参数时基线默认不选');
assert.equal(parseBaselineFilter(new URLSearchParams('baseline_id=12')), 12, '有效路由参数应回显基线');
assert.equal(parseBaselineFilter(new URLSearchParams('baseline_id=invalid')), undefined, '非法基线参数不能成为筛选条件');

const clearCompliance = buildTargetFilterSearch(
  new URLSearchParams('baseline_id=12&compliance_status=non_compliant'),
  { baselineId: 12, complianceStatus: undefined },
);
assert.equal(clearCompliance.get('baseline_id'), '12', '清空合规状态应保留当前基线');
assert.equal(clearCompliance.has('compliance_status'), false, '清空合规状态应移除路由参数');

const clearBaseline = buildTargetFilterSearch(
  clearCompliance,
  { baselineId: undefined, complianceStatus: undefined },
);
assert.equal(clearBaseline.has('baseline_id'), false, '清空基线应移除路由参数');

const page = readFileSync(
  resolve(process.cwd(), 'src/app/patch-manager/(pages)/target/page.tsx'),
  'utf8',
);
assert.match(page, /placeholder="基线"[\s\S]{0,500}allowClear/, '目标管理应提供可清空的基线下拉');
assert.match(page, /placeholder="基线"[\s\S]{0,500}showSearch/, '基线下拉应支持搜索');
assert.match(page, /page_size:\s*-1/, '基线选项应一次查询全部');
assert.match(page, /baseline_id:[\s\S]{0,150}baselineFilter/, '目标列表请求应携带当前基线条件');

console.log('目标管理基线筛选约束通过');
