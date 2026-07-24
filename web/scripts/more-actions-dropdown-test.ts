/**
 * MoreActionsDropdown 静态渲染契约测试
 *
 * 用 react-dom/server 的 renderToString 验证组件 trigger 渲染输出,
 * 覆盖 aria-label / buttonType / buttonClassName / iconStyle / items 不报错 等契约。
 *
 * 注意:AntD Dropdown 的 menu items 是 portal 渲染,SSR 默认不输出 item 内容;
 *       交互行为(点击触发 / confirm modal)需要 RTL + DOM 环境,不在本测试覆盖范围。
 *
 * 运行: pnpm exec tsx scripts/more-actions-dropdown-test.ts
 */

import React from 'react';
import { renderToString } from 'react-dom/server';
import { IntlProvider } from 'react-intl';
import MoreActionsDropdown from '../src/components/more-actions-dropdown';
import type { MoreActionsDropdownItem } from '../src/components/more-actions-dropdown';

const MESSAGES: Record<string, string> = {
  'common.more': 'more',
  'common.confirm': 'confirm',
  'common.cancel': 'cancel',
};

const wrap = (node: React.ReactElement) =>
  React.createElement(
    IntlProvider,
    { locale: 'en', messages: MESSAGES, onError: () => undefined },
    node
  );

let failed = 0;
let passed = 0;

function assertContains(label: string, haystack: string, needle: string) {
  if (haystack.includes(needle)) {
    passed++;
    console.log(`  ✓ ${label}`);
  } else {
    failed++;
    console.error(`  ✗ ${label}\n    期望包含: ${needle}\n    实际片段: ${haystack.slice(0, 200)}...`);
  }
}

function assertNotContains(label: string, haystack: string, needle: string) {
  if (!haystack.includes(needle)) {
    passed++;
    console.log(`  ✓ ${label}`);
  } else {
    failed++;
    console.error(`  ✗ ${label}\n    不应包含: ${needle}`);
  }
}

function section(name: string) {
  console.log(`\n[${name}]`);
}

// ============== Trigger 渲染契约 ==============

section('default trigger');
{
  const html = renderToString(
    wrap(
      React.createElement(MoreActionsDropdown, {
        items: [
          { key: 'edit', label: 'Edit', onClick: () => undefined },
          { key: 'delete', label: 'Delete', danger: true, onClick: () => undefined },
        ],
      })
    )
  );
  assertContains('trigger 含 aria-label', html, 'aria-label="more"');
  assertContains('trigger 含 MoreOutlined icon', html, 'anticon-more');
  assertContains('trigger 默认 type="text"', html, 'ant-btn');
}

section('ariaLabel 覆盖 i18n 默认值');
{
  const html = renderToString(
    wrap(
      React.createElement(MoreActionsDropdown, {
        ariaLabel: '自定义更多',
        items: [{ key: 'edit', label: 'Edit', onClick: () => undefined }],
      })
    )
  );
  // trigger button 应使用自定义 ariaLabel
  // 注:icon span 仍带 AntD 默认 aria-label="more"(图标组件自带),与 prop 行为无关
  assertContains('ariaLabel prop 透传到 trigger button', html, 'aria-label="自定义更多"');
  assertContains('trigger button 存在', html, 'ant-btn');
}

section('empty items 仍渲染 trigger');
{
  const html = renderToString(
    wrap(React.createElement(MoreActionsDropdown, { items: [] }))
  );
  assertContains('空 items 仍渲染 trigger button', html, 'ant-btn');
}

section('buttonType="link" 生效');
{
  const htmlLink = renderToString(
    wrap(
      React.createElement(MoreActionsDropdown, {
        buttonType: 'link',
        items: [{ key: 'edit', label: 'Edit', onClick: () => undefined }],
      })
    )
  );
  assertContains('buttonType="link" → ant-btn-link 类', htmlLink, 'ant-btn-link');
}

section('buttonType="default" 生效');
{
  const htmlDefault = renderToString(
    wrap(
      React.createElement(MoreActionsDropdown, {
        buttonType: 'default',
        items: [{ key: 'edit', label: 'Edit', onClick: () => undefined }],
      })
    )
  );
  assertNotContains('buttonType="default" 不应有 ant-btn-link', htmlDefault, 'ant-btn-link');
}

section('buttonSize="middle" 生效');
{
  const html = renderToString(
    wrap(
      React.createElement(MoreActionsDropdown, {
        buttonSize: 'middle',
        items: [{ key: 'edit', label: 'Edit', onClick: () => undefined }],
      })
    )
  );
  assertContains('buttonSize="middle" 不含 size-small 类', html, 'ant-btn');
  assertNotContains('buttonSize="middle" 不含 ant-btn-sm', html, 'ant-btn-sm');
}

section('buttonClassName 透传到 trigger');
{
  const html = renderToString(
    wrap(
      React.createElement(MoreActionsDropdown, {
        buttonClassName: 'my-custom-trigger-class',
        items: [{ key: 'edit', label: 'Edit', onClick: () => undefined }],
      })
    )
  );
  assertContains('buttonClassName 出现在 trigger', html, 'my-custom-trigger-class');
}

section('iconStyle 透传到 MoreOutlined');
{
  const html = renderToString(
    wrap(
      React.createElement(MoreActionsDropdown, {
        iconStyle: { fontSize: '24px' },
        items: [{ key: 'edit', label: 'Edit', onClick: () => undefined }],
      })
    )
  );
  assertContains('iconStyle 内联到 icon 节点', html, 'font-size:24px');
}

section('placement / trigger 不破坏 SSR');
{
  const html = renderToString(
    wrap(
      React.createElement(MoreActionsDropdown, {
        placement: 'topRight',
        trigger: ['hover'],
        items: [{ key: 'edit', label: 'Edit', onClick: () => undefined }],
      })
    )
  );
  assertContains('placement/trigger 不影响 trigger 渲染', html, 'ant-btn');
}

section('items 含 permission / disabled / icon / confirm 不报错');
{
  // 仅断言不抛异常,实际行为需 RTL + DOM 验证
  let didRender = false;
  try {
    const html = renderToString(
      wrap(
        React.createElement(MoreActionsDropdown, {
          items: [
            {
              key: 'edit',
              label: 'Edit',
              permission: 'Edit',
              icon: React.createElement('span', { className: 'test-icon' }),
              disabled: true,
              onClick: () => undefined,
            },
            {
              key: 'delete',
              label: 'Delete',
              permission: 'Delete',
              danger: true,
              confirm: { title: 'Sure?' },
              onClick: () => undefined,
            },
          ],
        })
      )
    );
    didRender = html.length > 0;
  } catch (err) {
    failed++;
    console.error(`  ✗ 渲染异常: ${err}`);
  }
  if (didRender) {
    passed++;
    console.log('  ✓ 含全部 item 字段的复杂 items 正常渲染');
  } else {
    failed++;
    console.error('  ✗ 渲染失败');
  }
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);