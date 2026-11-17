// @vitest-environment node
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { ChatMarkdown, renderChatMarkdown } from '../src/Markdown';

it('renders escaped text without a browser DOM and never emits raw HTML', () => {
  const content = '<img src="x" onerror="alert(1)"><script>alert(1)</script>';
  const rendered = renderToStaticMarkup(<ChatMarkdown content={content} />);
  expect(rendered).toContain('&lt;script&gt;');
  expect(rendered).not.toContain('<script>');
  expect(renderChatMarkdown(content, true)).not.toContain('<script>');
});
