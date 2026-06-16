import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import EllipsisWithTooltip from '../src/components/ellipsis-with-tooltip';

const maliciousAlertName =
  '<img src=x onerror=alert(1)><script>alert("xss")</script>-关键字分组测试';

const rendered = renderToStaticMarkup(
  <EllipsisWithTooltip text={maliciousAlertName} className="truncate w-full" />
);

assert.equal(rendered.includes('<img'), false);
assert.equal(rendered.includes('<script'), false);
assert.equal(rendered.includes('&lt;img'), true);
assert.equal(rendered.includes('&lt;script&gt;'), true);
assert.equal(rendered.includes('关键字分组测试'), true);

console.log('log-alert-render-security validation passed');
