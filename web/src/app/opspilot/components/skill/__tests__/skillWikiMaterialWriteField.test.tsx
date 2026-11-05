import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { Form } from 'antd';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SkillWikiMaterialWriteField from '../skillWikiMaterialWriteField';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

afterEach(cleanup);

beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
});

describe('SkillWikiMaterialWriteField', () => {
  it('sits with the knowledge base binding and defaults to off', () => {
    render(
      <Form initialValues={{ wiki_knowledge_bases: [], allow_wiki_material_write: false }}>
        <Form.Item label="wiki.title" name="wiki_knowledge_bases">
          <input aria-label="wiki.title" />
        </Form.Item>
        <SkillWikiMaterialWriteField />
      </Form>,
    );

    expect(screen.getByLabelText('wiki.title')).toBeTruthy();
    expect(screen.getByText('skill.form.allowWikiMaterialWrite')).toBeTruthy();
    const toggle = screen.getByRole('switch');
    expect(toggle.getAttribute('aria-checked')).toBe('false');
    expect(toggle.hasAttribute('disabled')).toBe(true);

    fireEvent.click(screen.getByText('skill.form.allowWikiMaterialWrite'));
    expect(toggle.getAttribute('aria-checked')).toBe('false');
  });

  it('enables the switch after a knowledge base is selected', () => {
    render(
      <Form initialValues={{ wiki_knowledge_bases: [1], allow_wiki_material_write: true }}>
        <Form.Item name="wiki_knowledge_bases">
          <input aria-label="wiki.title" />
        </Form.Item>
        <SkillWikiMaterialWriteField />
      </Form>,
    );

    const toggle = screen.getByRole('switch');
    expect(toggle.hasAttribute('disabled')).toBe(false);
    expect(toggle.getAttribute('aria-checked')).toBe('true');
  });
});
