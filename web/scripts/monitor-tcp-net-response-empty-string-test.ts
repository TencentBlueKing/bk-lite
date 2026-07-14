/**
 * 回归测试：TCP 拨测(net_response)提交时,用户留空「发送内容」「期望返回」,
 * 不会因为 formData 缺 key 导致后端 Jinja2 模板 {{ 字段名 }} 抛 UndefinedError
 * (前端报错："渲染采集模板失败")。
 *
 * 根因:前端表单只回填用户实际改过的字段;用户从未碰过 send/expect,
 * formData 中不含这两个 key,后端模板渲染时报 UndefinedError。
 *
 * 修复:usePluginFromJson 中新增 fillOptionalFormFields,把 formFields 中
 * required!==true 且 formData 未包含的字段补成空串。后端 child.toml.j2 的
 * `{% if 字段 %}{% endif %}` 会跳过空串,保留可选语义,避免渲染失败。
 */
import assert from 'node:assert/strict';

import { fillOptionalFormFields } from '../src/app/monitor/hooks/integration/usePluginFromJson';

const tcpFormFields = [
  { name: 'host', required: true, type: 'input' },
  { name: 'port', required: true, type: 'inputNumber' },
  { name: 'interval', required: true, type: 'inputNumber' },
  { name: 'timeout', required: false, type: 'inputNumber' },
  { name: 'send', required: false, type: 'input' },
  { name: 'expect', required: false, type: 'input' }
];

// 场景 1: 用户只填了必填字段,send/expect 留空
const filled1 = fillOptionalFormFields(
  { host: 'aaxcemon.hkairport.com', port: 443, interval: 10 },
  tcpFormFields
);
assert.deepEqual(filled1, {
  host: 'aaxcemon.hkairport.com',
  port: 443,
  interval: 10,
  timeout: '',
  send: '',
  expect: ''
}, '非必填且未填的字段必须补成空串');

// 场景 2: 用户填了部分非必填字段
const filled2 = fillOptionalFormFields(
  { host: 'example.com', port: 22, interval: 10, send: 'PING\r\n' },
  tcpFormFields
);
assert.equal(filled2.send, 'PING\r\n', '用户填的字段必须原样保留');
assert.equal(filled2.expect, '', '用户未填的非必填字段必须补成空串');
assert.equal(filled2.timeout, '', '用户未填的非必填字段必须补成空串');

// 场景 3: 必填字段缺失不动 —— 留给前端表单校验拦截
const filled3 = fillOptionalFormFields({ port: 443, interval: 10 }, tcpFormFields);
assert.equal(filled3.host, undefined, '必填字段缺失时不应被兜底成空串');

// 场景 4: 用户显式传 null 时,不应该再补空串(用户主动清空 ≠ 未填)
const filled4 = fillOptionalFormFields(
  { host: 'x.com', port: 80, interval: 10, send: null as any },
  tcpFormFields
);
assert.equal(filled4.send, null, '用户显式传 null 不应被覆盖成空串');

// 场景 5: formFields 为空时直接返回原对象(避免无谓拷贝)
const input5 = { host: 'a.com' };
const out5 = fillOptionalFormFields(input5, undefined);
assert.deepEqual(out5, input5);

const out6 = fillOptionalFormFields(input5, []);
assert.deepEqual(out6, input5);

// 场景 6: 原对象不被修改(不可变)
const input7 = { host: 'a.com' };
const out7 = fillOptionalFormFields(input7, tcpFormFields);
assert.notStrictEqual(out7, input7, '应返回新对象,不修改原对象');
assert.equal(input7.send, undefined, '原对象 send 仍为 undefined');

console.log('✓ fillOptionalFormFields 兜底逻辑测试通过');
