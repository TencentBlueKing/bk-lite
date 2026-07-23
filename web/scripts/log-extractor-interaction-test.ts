import assert from 'node:assert/strict';
import {
  flattenExtractorPaths,
  moveExtractorItem,
  normalizeExtractorSamples,
  reorderExtractorItem,
  shouldShowExtractorHeaderAdd
} from '../src/app/log/(pages)/integration/receive/logExtractorLogic';

assert.deepEqual(
  Array.from(
    flattenExtractorPaths({ http: { status: 200, 'request.id': 'a' } })
  ),
  ['http', 'http.status', 'http["request.id"]'],
  '属性选择器应生成规范嵌套路径和引用段'
);

assert.deepEqual(
  normalizeExtractorSamples({ data: [{ message: 'one' }, null, 'bad'] }),
  [{ message: 'one' }],
  '历史样本响应应只保留事件对象'
);

assert.deepEqual(
  moveExtractorItem([1, 2, 3], 1, -1),
  [2, 1, 3],
  '键盘上移应生成完整新顺序'
);
assert.equal(moveExtractorItem([1, 2, 3], 0, -1), null, '不能越过顺序边界');
assert.deepEqual(
  reorderExtractorItem([1, 2, 3, 4], 0, 2),
  [2, 3, 1, 4],
  '拖拽必须产生完整的新顺序'
);
assert.equal(reorderExtractorItem([1, 2, 3], 1, 1), null, '原地拖拽不提交');

assert.equal(
  shouldShowExtractorHeaderAdd(true, 0),
  false,
  '空状态应只保留表格内的新建入口'
);
assert.equal(
  shouldShowExtractorHeaderAdd(true, 1),
  true,
  '已有规则时应在抽屉头部显示新建入口'
);
assert.equal(
  shouldShowExtractorHeaderAdd(false, 1),
  false,
  '无操作权限时不应显示新建入口'
);

console.log('log-extractor-interaction tests passed');
