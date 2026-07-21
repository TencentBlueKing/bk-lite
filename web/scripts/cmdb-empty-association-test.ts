import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const source = readFileSync(
  resolve(
    process.cwd(),
    'src/app/cmdb/(pages)/assetData/detail/relationships/selectInstance.tsx'
  ),
  'utf8'
);

assert.match(
  source,
  /if \(_modelId\) \{\s*initPage\(_modelId\);\s*\} else \{[\s\S]*setIntancePropertyList\(\[\]\);[\s\S]*setTableData\(\[\]\);[\s\S]*setLoading\(false\);[\s\S]*\}/,
  '没有模型关系时不得使用空 model_id 初始化属性和实例请求'
);

assert.match(
  source,
  /value=\{relationList\.length \? assoModelId : undefined\}/,
  '没有模型关系时，下拉框不应显示内部默认值 0'
);

console.log('PASS cmdb-empty-association');
