import assert from 'node:assert/strict';
import { describe, it } from 'vitest';
import {
  getDataSourceFormParamInitialValue,
  mergeRestoredParamValue,
} from '@/app/ops-analysis/utils/dataSourceFormParams';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';

const page = (value: ParamItem['value']): ParamItem => ({
  name: 'page',
  alias_name: '页码',
  type: 'number',
  filterType: 'params',
  value,
});

describe('generic query paging defaults', () => {
  it('shows the seed number and keeps an explicit saved page', () => {
    assert.equal(getDataSourceFormParamInitialValue(page(1)), 1);
    assert.equal(getDataSourceFormParamInitialValue({ ...page(20), name: 'page_size' }), 20);
    assert.equal(mergeRestoredParamValue(1, page(null)), 1);
    assert.equal(mergeRestoredParamValue(20, { ...page(null), name: 'page_size' }), 20);
    assert.equal(mergeRestoredParamValue(1, page(3)), 3);
    assert.equal(mergeRestoredParamValue(20, { ...page(50), name: 'page_size' }), 50);
  });

  it('still restores an empty value for params other than paging', () => {
    assert.equal(mergeRestoredParamValue('host', {
      name: 'model_id',
      alias_name: '模型',
      type: 'string',
      value: null,
    }), null);
  });
});
