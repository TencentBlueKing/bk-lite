import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import RepairCommandsCard from '../src/app/opspilot/components/custom-chat-sse/RepairCommandsCard';

const html = renderToStaticMarkup(
  <RepairCommandsCard
    commands={{
      commands_id: 'repair-1',
      received_at: Date.now(),
      commands_markdown: `**未配置存活探针**

\`\`\`bash
kubectl patch deployment nginx-test -n default --type=strategic -p "$PATCH"
\`\`\``,
    }}
  />
);

assert.match(html, /修复命令/);
assert.match(html, /kubectl patch deployment nginx-test/);
assert.equal(html.includes('bg-gray-900'), false);
assert.equal(html.includes('text-green-300'), false);
assert.match(html, /bg-\[var\(--color-fill-1\)\]/);
assert.match(html, /text-\[var\(--color-text-1\)\]/);

console.log('repair commands card test passed');
