// @vitest-environment jsdom

import React from 'react';
import { Form } from 'antd';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

const INST_UUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const OTHER_UUID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

const apis = vi.hoisted(() => ({
  getModelList: vi.fn(async () => [{ model_id: 'host', model_name: 'Host' }]),
  searchInstances: vi.fn(async () => ({
    insts: [{ inst_uuid: INST_UUID, inst_name: 'web-1' }],
  })),
  getInstanceDetail: vi.fn(async () => ({
    inst_uuid: INST_UUID,
    model_id: 'host',
    inst_name: 'web-1',
  })),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/app/cmdb/api', () => ({
  useModelApi: () => ({
    getModelList: async (...args: unknown[]) => apis.getModelList(...args),
  }),
  useInstanceApi: () => ({
    searchInstances: async (...args: unknown[]) => apis.searchInstances(...args),
    getInstanceDetail: async (...args: unknown[]) =>
      apis.getInstanceDetail(...args),
  }),
}));

import {
  RelatedTopologyAssetField,
  instanceOptionFromEntity,
  mergePinnedInstanceOption,
} from '../relatedTopologyAssetField';

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

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function RelatedTopologyValuesProbe() {
  const form = Form.useFormInstance();
  const values = Form.useWatch('relatedTopology', form);
  return <pre data-testid="related-topology-values">{JSON.stringify(values)}</pre>;
}

describe('relatedTopology asset field fetch once', () => {
  it('does not retrigger instance search when API identities change each render', async () => {
    render(
      <Form initialValues={{ relatedTopology: { modelId: 'host' } }}>
        <RelatedTopologyAssetField open enabled />
      </Form>,
    );
    await waitFor(() => {
      expect(apis.searchInstances).toHaveBeenCalledTimes(1);
    });
    expect(apis.getModelList).toHaveBeenCalledTimes(1);
    expect(apis.getInstanceDetail).not.toHaveBeenCalled();
    const settled = apis.searchInstances.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 80));
    expect(apis.searchInstances.mock.calls.length).toBe(settled);
  });

  it('keeps persisted modelId and instUuid as form values after reopen', async () => {
    const persisted = { modelId: 'host', instUuid: INST_UUID };
    render(
      <Form initialValues={{ relatedTopology: persisted }}>
        <RelatedTopologyAssetField open enabled />
        <RelatedTopologyValuesProbe />
      </Form>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('related-topology-values').textContent).toContain(
        INST_UUID,
      );
    });
    expect(JSON.parse(screen.getByTestId('related-topology-values').textContent || '{}')).toEqual(
      persisted,
    );
    await waitFor(() => {
      expect(apis.searchInstances).toHaveBeenCalled();
    });
    expect(screen.getByText('web-1')).toBeTruthy();
  });

  it('pins the current instUuid when it is missing from the first page', async () => {
    apis.searchInstances.mockResolvedValueOnce({
      insts: [{ inst_uuid: OTHER_UUID, inst_name: 'other-1' }],
    });
    render(
      <Form initialValues={{ relatedTopology: { modelId: 'host', instUuid: INST_UUID } }}>
        <RelatedTopologyAssetField open enabled />
      </Form>,
    );
    await waitFor(() => {
      expect(apis.getInstanceDetail).toHaveBeenCalledWith(INST_UUID);
    });
    await waitFor(() => {
      expect(screen.getByText('web-1')).toBeTruthy();
    });
  });

  it('marks both model and instance as required before save', async () => {
    const onFinish = vi.fn();
    render(
      <Form onFinish={onFinish}>
        <RelatedTopologyAssetField open enabled />
        <button type="submit">save</button>
      </Form>,
    );
    fireEvent.click(screen.getByText('save'));
    await waitFor(() => {
      expect(screen.getAllByText('dashboard.relatedTopologyModelIdRequired').length).toBeGreaterThan(0);
      expect(screen.getAllByText('dashboard.relatedTopologyInstUuidRequired').length).toBeGreaterThan(0);
    });
    expect(onFinish).not.toHaveBeenCalled();
  });
});

describe('relatedTopology instance option pin', () => {
  it('keeps the current instance when it is absent from the first page', () => {
    const listed = [
      { value: OTHER_UUID, label: 'other-1' },
    ];
    const pinned = instanceOptionFromEntity({
      inst_uuid: INST_UUID,
      inst_name: 'web-1',
    });
    expect(mergePinnedInstanceOption(listed, pinned)).toEqual([
      { value: INST_UUID, label: 'web-1' },
      { value: OTHER_UUID, label: 'other-1' },
    ]);
    expect(mergePinnedInstanceOption(listed, listed[0])).toEqual(listed);
  });
});
