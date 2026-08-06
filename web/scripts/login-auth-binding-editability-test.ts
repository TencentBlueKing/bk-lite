import assert from 'node:assert/strict';

import { isBuiltinLoginAuthBinding } from '../src/app/system-manager/utils/loginAuthFormUtils';

assert.equal(isBuiltinLoginAuthBinding('bk_lite_builtin'), true);
assert.equal(isBuiltinLoginAuthBinding('feishu'), false);
assert.equal(isBuiltinLoginAuthBinding(undefined), false);

console.log('login auth binding editability tests passed');
