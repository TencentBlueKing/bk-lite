import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { Form } from 'antd';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});
import { CardListSettingsSection } from '../cardListSettingsSection';
import type { CardListFormState } from '../../utils/cardListSettingsModel';

const fields = [
  { key: 'name', title: '名称', value_type: 'string' as const },
  { key: 'summary', title: '摘要', value_type: 'string' as const },
  { key: 'severity', title: '级别', value_type: 'string' as const },
  { key: 'owner', title: '负责人', value_type: 'string' as const },
];

const Harness = ({
  initial,
}: {
  initial?: CardListFormState;
}) => {
  const [form] = Form.useForm();
  const [dump, setDump] = useState('');

  return (
    <Form
      form={form}
      initialValues={{
        cardList: {
          leading: { type: 'none' },
          layout: 'list',
          ...initial,
        },
      }}
    >
      <CardListSettingsSection
        t={(key) => key}
        availableFields={fields}
      />
      <button
        type="button"
        onClick={() =>
          form.setFieldValue(['cardList', 'titleField'], 'name')
        }
      >
        seed-title
      </button>
      <button
        type="button"
        onClick={() =>
          form.setFieldsValue({
            cardList: {
              titleField: 'name',
              descriptionField: 'summary',
              leading: { type: 'index' },
              badgeField: 'severity',
              trailingPrimaryField: 'owner',
            },
          })
        }
      >
        seed-all-slots
      </button>
      <button
        type="button"
        onClick={() => setDump(JSON.stringify(form.getFieldsValue().cardList))}
      >
        dump-form
      </button>
      <pre data-testid="form-dump">{dump}</pre>
    </Form>
  );
};

afterEach(cleanup);

describe('CardListSettingsSection', () => {
  it('shows title config and keeps optional groups collapsed by default', () => {
    render(<Harness />);

    expect(screen.getByText('dashboard.cardListTitleField')).toBeTruthy();
    expect(screen.getByText('dashboard.cardListDescriptionField')).toBeTruthy();
    expect(
      screen.getByTestId('card-list-optional-leading').getAttribute('aria-expanded'),
    ).toBe('false');
    expect(
      screen.getByTestId('card-list-optional-badge').getAttribute('aria-expanded'),
    ).toBe('false');
    expect(
      screen.getByTestId('card-list-optional-trailing').getAttribute('aria-expanded'),
    ).toBe('false');
    expect(screen.getAllByText('dashboard.cardListExpand').length).toBe(3);
    expect(screen.getByTestId('card-list-preview').textContent).toContain(
      'dashboard.cardListPreview',
    );
    expect(screen.getByTestId('card-list-preview').textContent).toContain(
      'dashboard.cardListPreviewTitle',
    );
  });

  it('restores optional groups and preview when editing an existing cardList', () => {
    render(
      <Harness
        initial={{
          titleField: 'name',
          leading: { type: 'field', field: 'severity' },
          badgeField: 'severity',
          trailingPrimaryField: 'owner',
          layout: 'grid',
        }}
      />,
    );

    expect(
      screen.getByTestId('card-list-optional-leading').getAttribute('aria-expanded'),
    ).toBe('true');
    expect(
      screen.getByTestId('card-list-optional-badge').getAttribute('aria-expanded'),
    ).toBe('true');
    expect(
      screen.getByTestId('card-list-optional-trailing').getAttribute('aria-expanded'),
    ).toBe('true');
    expect(screen.queryByText('dashboard.cardListLeadingMode')).toBeNull();
    expect(screen.getByTestId('card-list-optional-badge-hint')).toBeTruthy();
    expect(screen.queryByText('dashboard.cardListBadgeHint')).toBeNull();
    expect(screen.getByText('dashboard.cardListTrailingFirst')).toBeTruthy();
    expect(screen.getAllByText('dashboard.cardListFieldUsedIn').length).toBeGreaterThan(0);
    expect(
      screen.getByTestId('card-list-optional-leading').textContent,
    ).toContain('*');
    expect(screen.getByTestId('card-list-preview').textContent).toContain('名称');
    expect(screen.getByTestId('card-list-preview').textContent).toContain('级别');
    expect(screen.getByTestId('card-list-preview').textContent).toContain('负责人');
    expect(
      screen.getByText('dashboard.cardListLayoutGrid').closest('button')
        ?.getAttribute('aria-pressed'),
    ).toBe('true');
  });

  it('collapses optional groups without clearing form values or preview', () => {
    render(
      <Harness
        initial={{
          titleField: 'name',
          descriptionField: 'summary',
          leading: { type: 'index' },
          badgeField: 'severity',
          trailingPrimaryField: 'owner',
        }}
      />,
    );

    fireEvent.click(screen.getByTestId('card-list-optional-badge'));
    fireEvent.click(screen.getByTestId('card-list-optional-trailing'));
    expect(
      screen.getByTestId('card-list-optional-badge').getAttribute('aria-expanded'),
    ).toBe('false');
    expect(
      screen.getByTestId('card-list-optional-trailing').getAttribute('aria-expanded'),
    ).toBe('false');

    const preview = screen.getByTestId('card-list-preview');
    expect(preview.textContent).toContain('名称');
    expect(preview.textContent).toContain('摘要');
    expect(preview.textContent).toContain('01');
    expect(preview.textContent).toContain('级别');
    expect(preview.textContent).toContain('负责人');

    fireEvent.click(screen.getByText('dump-form'));
    const dumped = JSON.parse(screen.getByTestId('form-dump').textContent || '{}');
    expect(dumped.badgeField).toBe('severity');
    expect(dumped.trailingPrimaryField).toBe('owner');
    expect(dumped.leading?.type).toBe('index');
  });

  it('switches leading modes and layout and shows the selected layout', () => {
    render(<Harness initial={{ titleField: 'name' }} />);

    fireEvent.click(screen.getByTestId('card-list-optional-leading'));
    expect(screen.getByText('dashboard.cardListLeadingNone')).toBeTruthy();
    expect(screen.getByText('dashboard.cardListLeadingIndex')).toBeTruthy();
    expect(screen.getByText('dashboard.cardListLeadingField')).toBeTruthy();
    expect(screen.queryByText('dashboard.cardListLeadingMode')).toBeNull();

    fireEvent.click(screen.getByText('dashboard.cardListLeadingField'));
    expect(
      screen.getByTestId('card-list-optional-leading').textContent,
    ).toContain('*');
    expect(
      screen.getAllByText('dashboard.cardListSelectField').length,
    ).toBeGreaterThan(0);

    const listButton = screen
      .getByText('dashboard.cardListLayoutList')
      .closest('button');
    const gridButton = screen
      .getByText('dashboard.cardListLayoutGrid')
      .closest('button');
    expect(listButton?.getAttribute('aria-pressed')).toBe('true');
    expect(gridButton?.getAttribute('aria-pressed')).toBe('false');

    fireEvent.click(screen.getByText('dashboard.cardListLayoutGrid'));
    expect(listButton?.getAttribute('aria-pressed')).toBe('false');
    expect(gridButton?.getAttribute('aria-pressed')).toBe('true');

    fireEvent.click(screen.getByText('dump-form'));
    const dumped = JSON.parse(screen.getByTestId('form-dump').textContent || '{}');
    expect(dumped.layout).toBe('grid');
    expect(dumped.leading?.type).toBe('field');
  });

  it('updates preview slots from current form state', () => {
    render(<Harness />);

    fireEvent.click(screen.getByText('seed-all-slots'));
    const preview = screen.getByTestId('card-list-preview');
    expect(preview.textContent).toContain('名称');
    expect(preview.textContent).toContain('摘要');
    expect(preview.textContent).toContain('01');
    expect(preview.textContent).toContain('级别');
    expect(preview.textContent).toContain('负责人');
  });
});
