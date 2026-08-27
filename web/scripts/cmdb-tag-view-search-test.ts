import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  buildAttrSearchCondition,
  defaultSearchField,
  searchableAttrs,
} from '../src/app/cmdb/(pages)/views/scene/attrSearchCondition';
import {
  getTagViewSearchStorageKey,
  parseModelSearches,
  readModelSearches,
  toSearchPayload,
  writeModelSearch,
  type ModelSearchPreference,
} from '../src/app/cmdb/(pages)/views/scene/tagViewSearchPreference';
import type { AttrFieldType } from '../src/app/cmdb/types/assetManage';

class MemoryStorage {
  private values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }
}

const attr = (
  attr_id: string,
  attr_type: string,
  extra: Partial<AttrFieldType> = {}
): AttrFieldType => ({
  attr_id,
  attr_name: attr_id,
  attr_type,
  is_required: false,
  editable: false,
  option: [],
  ...extra,
});

assert.deepEqual(
  searchableAttrs([attr('inst_name', 'str'), attr('photo', 'image'), attr('files', 'attachment')]).map(
    (item) => item.attr_id
  ),
  ['inst_name']
);
assert.equal(defaultSearchField([attr('ip_addr', 'str'), attr('inst_name', 'str')]), 'inst_name');

assert.deepEqual(buildAttrSearchCondition(attr('inst_name', 'str'), '  10.11  '), {
  field: 'inst_name',
  type: 'str*',
  value: '10.11',
});
assert.deepEqual(buildAttrSearchCondition(attr('inst_name', 'str'), 'core', true), {
  field: 'inst_name',
  type: 'str=',
  value: 'core',
});
assert.deepEqual(buildAttrSearchCondition(attr('owner', 'user'), ['alice', 'bob']), {
  field: 'owner',
  type: 'list[]',
  value: ['alice', 'bob'],
});
assert.deepEqual(buildAttrSearchCondition(attr('tag', 'tag'), ['env:test']), {
  field: 'tag',
  type: 'list_any[]',
  value: ['env:test'],
  accurate: true,
});
assert.equal(buildAttrSearchCondition(attr('inst_name', 'str'), '   '), null);

const storage = new MemoryStorage();
assert.equal(getTagViewSearchStorageKey(12), 'bk-lite:cmdb:tag-view-search:v1:12');

assert.deepEqual(parseModelSearches({ host: '  10.11  ' }).host, {
  field: 'inst_name',
  value: '10.11',
  exact: false,
  clause: { field: 'inst_name', type: 'str*', value: '10.11' },
});

const ipSearch: ModelSearchPreference = {
  field: 'ip_addr',
  value: '10.11',
  exact: false,
  clause: { field: 'ip_addr', type: 'str*', value: '10.11' },
};
assert.deepEqual(writeModelSearch(storage, 12, 'host', ipSearch).host, ipSearch);
assert.deepEqual(readModelSearches(storage, 12).host, ipSearch);
assert.deepEqual(readModelSearches(storage, 13), {});
assert.deepEqual(toSearchPayload({ host: ipSearch, switch: { field: 'inst_name' } }), {
  host: { field: 'ip_addr', type: 'str*', value: '10.11' },
});

writeModelSearch(storage, 12, 'host', { field: 'ip_addr', clause: null });
assert.equal(toSearchPayload(readModelSearches(storage, 12)).host, undefined);

storage.setItem(getTagViewSearchStorageKey(14), '{bad json');
assert.deepEqual(readModelSearches(storage, 14), {});

const root = path.dirname(fileURLToPath(import.meta.url));
const pageSrc = fs.readFileSync(
  path.join(root, '../src/app/cmdb/(pages)/views/scene/page.tsx'),
  'utf8'
);
assert.match(pageSrc, /readModelSearches/);
assert.match(pageSrc, /writeModelSearch/);
assert.match(pageSrc, /toSearchPayload/);
assert.match(pageSrc, /searches:/);
assert.match(pageSrc, /getModelAttrList/);

const sectionSrc = fs.readFileSync(
  path.join(root, '../src/app/cmdb/(pages)/views/scene/modelResultSection.tsx'),
  'utf8'
);
assert.match(sectionSrc, /ModelAttrSearch/);
assert.equal(sectionSrc.includes('Input.Search'), false);

const searchSrc = fs.readFileSync(
  path.join(root, '../src/app/cmdb/(pages)/views/scene/modelAttrSearch.tsx'),
  'utf8'
);
assert.match(searchSrc, /searchableAttrs/);
assert.match(searchSrc, /buildAttrSearchCondition/);
assert.match(searchSrc, /Model.isExactSearch_abbreviation/);

const apiSrc = fs.readFileSync(
  path.join(root, '../src/app/cmdb/api/sceneView.ts'),
  'utf8'
);
assert.match(apiSrc, /field: string/);
assert.match(apiSrc, /type: string/);

console.log('cmdb-tag-view-search-test: PASS');
