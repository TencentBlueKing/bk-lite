import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { isValidElement, type ReactElement } from 'react';
import {
  getRequestErrorPresentation,
  NETWORK_WHITELIST_REQUIRED,
  renderRequestErrorPresentation,
} from '../src/utils/requestErrorPresentation';

const presentation = getRequestErrorPresentation({
  code: NETWORK_WHITELIST_REQUIRED,
  message: '目标 IP 不在白名单内，请前往系统管理的白名单管理中添加。',
  data: {
    network_whitelist_url: '/system-manager/settings/network-whitelist',
    action_label: '前往白名单管理',
  },
});

assert.deepEqual(presentation, {
  message: '目标 IP 不在白名单内，请前往系统管理的白名单管理中添加。',
  actionLabel: '前往白名单管理',
  href: '/system-manager/settings/network-whitelist',
  target: '_blank',
  rel: 'noopener noreferrer',
});
assert.ok(presentation);
const rendered = renderRequestErrorPresentation(presentation);
assert.ok(isValidElement(rendered));
const renderedElement = rendered as ReactElement<{ children: unknown[] }>;
const link = renderedElement.props.children[2] as ReactElement<{
  href: string;
  target: string;
  rel: string;
}>;
assert.equal(link.props.href, '/system-manager/settings/network-whitelist');
assert.equal(link.props.target, '_blank');
assert.equal(link.props.rel, 'noopener noreferrer');

const requestSource = readFileSync(new URL('../src/utils/request.ts', import.meta.url), 'utf8');
assert.match(
  requestSource,
  /new HandledRequestError\(messageText,[\s\S]*presentation: presentation \?\? undefined/,
);

const channelModalSource = readFileSync(
  new URL('../src/app/system-manager/components/channel/channelModal.tsx', import.meta.url),
  'utf8',
);
assert.doesNotMatch(channelModalSource, /testError/);
assert.doesNotMatch(channelModalSource, /<Alert/);
assert.equal(getRequestErrorPresentation({ code: 'OTHER_ERROR' }), null);
assert.equal(
  getRequestErrorPresentation({
    code: NETWORK_WHITELIST_REQUIRED,
    data: { network_whitelist_url: 'javascript:alert(1)' },
  }),
  null,
);

console.log('opspilot network whitelist error presentation: pass');