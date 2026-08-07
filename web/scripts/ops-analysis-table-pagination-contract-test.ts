import assert from 'node:assert/strict';

import {
  buildTableQueryParams,
  supportsServerPagination,
} from '../src/app/ops-analysis/utils/tablePagination';
import { parseTableLikeData } from '../src/app/ops-analysis/components/widgets/shared/tableLikeData';
import { parseTableLikeData as parseShowcaseTableLikeData } from '../src/app/ops-analysis/components/ops-analysis-widgets/table-like-data';
import { buildWidgetExtraParams } from '../src/app/ops-analysis/utils/widgetDataTransform';

assert.equal(
  parseShowcaseTableLikeData,
  parseTableLikeData,
  '两套表格入口应复用同一个数据解析实现',
);

const unpagedParams = [
  { name: 'limit', value: 10 },
];
const partialPaginationParams = [
  { name: 'page', value: 1 },
];
const pagedParams = [
  { name: 'page', value: 1 },
  { name: 'page_size', value: 20 },
];

assert.equal(supportsServerPagination(unpagedParams), false);
assert.equal(supportsServerPagination(partialPaginationParams), false);
assert.equal(supportsServerPagination(pagedParams), true);

assert.deepEqual(
  buildTableQueryParams({
    dataSourceParams: unpagedParams,
    queryParams: {
      page: 2,
      page_size: 20,
      query_list: [{ field: 'title', type: 'str*', value: 'CPU' }],
    },
  }),
  {
    query_list: [{ field: 'title', type: 'str*', value: 'CPU' }],
  },
  '未声明分页的数据源不应携带 page/page_size',
);

assert.deepEqual(
  buildTableQueryParams({
    dataSourceParams: pagedParams,
    queryParams: {},
  }),
  { page: 1, page_size: 20 },
  '分页数据源的首次请求应使用表格默认值',
);

assert.deepEqual(
  buildTableQueryParams({
    dataSourceParams: pagedParams,
    queryParams: { page: 3, page_size: 20 },
  }),
  { page: 3, page_size: 20 },
  '分页数据源应携带当前页码和每页数量',
);

const fullRows = Array.from({ length: 238 }, (_, index) => ({ id: index + 1 }));
const unpagedArray = parseTableLikeData(fullRows, { current: 1, pageSize: 20 }, false);
assert.equal(unpagedArray.rows.length, 238);
assert.equal(unpagedArray.isPaginated, false);

const wrappedButUnpaged = parseTableLikeData(
  { items: fullRows.slice(0, 10), count: 10 },
  { current: 1, pageSize: 20 },
  false,
);
assert.equal(wrappedButUnpaged.rows.length, 10);
assert.equal(wrappedButUnpaged.isPaginated, false);

const pagedResponse = parseTableLikeData(
  { items: fullRows.slice(0, 20), count: 238 },
  { current: 2, pageSize: 20 },
  true,
);
assert.equal(pagedResponse.isPaginated, true);
assert.deepEqual(pagedResponse.pagination, {
  current: 2,
  pageSize: 20,
  total: 238,
});

const missingCount = parseTableLikeData(
  { items: fullRows.slice(0, 20) },
  { current: 1, pageSize: 20 },
  true,
);
assert.equal(missingCount.isPaginated, false);

assert.deepEqual(
  buildWidgetExtraParams({
    isTableLikeChart: true,
    tableQueryParams: { page: 2, page_size: 20 },
    runtimeParams: {},
    dataSourceParams: unpagedParams,
  }),
  {},
  '表格请求组装入口也必须移除未声明的分页参数',
);

assert.deepEqual(
  buildWidgetExtraParams({
    isTableLikeChart: true,
    tableQueryParams: {},
    runtimeParams: {},
    dataSourceParams: pagedParams,
  }),
  { page: 1, page_size: 20 },
  '表格请求组装入口应为分页数据源补齐默认分页参数',
);

const showcaseWrappedButUnpaged = parseShowcaseTableLikeData(
  { items: fullRows.slice(0, 10), count: 10 },
  { current: 1, pageSize: 20 },
  false,
);
assert.equal(
  showcaseWrappedButUnpaged.isPaginated,
  false,
  '组件展示入口必须遵循相同的分页能力契约',
);

console.log('ops analysis table pagination contract tests passed');
