import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { Form } from 'antd';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import React, { useEffect } from 'react';
import { SingleValueSettingsSection } from '../singleValueSettingsSection';

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

afterEach(cleanup);

const noop = () => undefined;

const Section = () => (
  <SingleValueSettingsSection
    t={(key) => key}
    selectedDataSource={{ id: 1 }}
    singleValueTreeData={[]}
    selectedFields={['value']}
    loadingSingleValueData={false}
    thresholdColors={[]}
    onFetchSingleValueDataFields={noop}
    onSingleValueFieldChange={noop}
    onThresholdChange={noop}
    onThresholdBlur={noop}
    onAddThreshold={noop}
    onRemoveThreshold={noop}
    compareAvailable
  />
);

const dumpCompareMode = (form: { getFieldValue: (name: string) => unknown }) => {
  const node = document.getElementById('compare-mode-dump');
  if (node) {
    node.textContent = String(form.getFieldValue('compareMode') ?? '');
  }
};

const Harness = ({
  initialCompareMode,
}: {
  initialCompareMode?: 'percent' | 'value';
}) => {
  const [form] = Form.useForm();

  return (
    <Form form={form} initialValues={{ compare: false, compareMode: initialCompareMode }}>
      <Section />
      <button type="button" onClick={() => dumpCompareMode(form)}>
        dump-compare-mode
      </button>
      <div id="compare-mode-dump" />
    </Form>
  );
};

const TopologyEditHarness = () => {
  const [form] = Form.useForm();

  useEffect(() => {
    form.setFieldsValue({ compare: true, compareMode: 'value' });
  }, [form]);

  return (
    <Form form={form}>
      <Section />
      <button type="button" onClick={() => dumpCompareMode(form)}>
        dump-compare-mode
      </button>
      <div id="compare-mode-dump" />
    </Form>
  );
};

describe('SingleValueSettingsSection compare mode', () => {
  it('defaults compare display to percent when period compare is turned on', () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole('switch'));
    fireEvent.click(screen.getByText('dump-compare-mode'));

    expect(document.getElementById('compare-mode-dump')?.textContent).toBe(
      'percent',
    );
    expect(screen.getByText('dashboard.compareModePercent')).toBeTruthy();
  });

  it('keeps numeric compare display after switching away from percent', () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole('switch'));
    fireEvent.mouseDown(screen.getByLabelText('dashboard.compareMode'));
    fireEvent.click(screen.getByText('dashboard.compareModeValue'));
    fireEvent.click(screen.getByText('dump-compare-mode'));

    expect(document.getElementById('compare-mode-dump')?.textContent).toBe(
      'value',
    );
  });

  it('does not reset an edited numeric compare mode when the field first mounts', () => {
    render(<TopologyEditHarness />);

    fireEvent.click(screen.getByText('dump-compare-mode'));

    expect(document.getElementById('compare-mode-dump')?.textContent).toBe(
      'value',
    );
  });
});
