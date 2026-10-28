import React from 'react';
import { cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import FilterBindingPanel from '@/app/ops-analysis/components/unifiedFilter/filterBindingPanel';
import OpsFilterBindingPanel from '@/app/ops-analysis/components/ops-analysis-unified-filter/filterBindingPanel';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';

const FILTER_ID = 'organization__string';

const definitions: UnifiedFilterDefinition[] = [
  {
    id: FILTER_ID,
    key: 'organization',
    name: '组织',
    type: 'string',
    enabled: true,
    order: 0,
    defaultValue: null,
  },
];

const disabledDefinitions: UnifiedFilterDefinition[] = [
  { ...definitions[0], enabled: false },
];

const params: ParamItem[] = [
  {
    name: 'organization',
    alias_name: '组织',
    type: 'string',
    filterType: 'filter',
    value: null,
  },
];

afterEach(() => {
  cleanup();
});

describe.each([
  ['dashboard', FilterBindingPanel],
  ['ops-analysis', OpsFilterBindingPanel],
])('%s filter linkage switch', (_label, Panel) => {
  it('writes explicit false when a followed filter is turned off', () => {
    const onChange = vi.fn();
    const view = render(
      <Panel
        definitions={definitions}
        dataSourceParams={params}
        filterBindings={{}}
        onChange={onChange}
      />,
    );
    const toggle = view.getByRole('switch');
    expect(toggle.getAttribute('aria-checked')).toBe('true');
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith({ [FILTER_ID]: false });
  });

  it('writes true when an opted-out filter is turned on', () => {
    const onChange = vi.fn();
    const view = render(
      <Panel
        definitions={definitions}
        dataSourceParams={params}
        filterBindings={{ [FILTER_ID]: false }}
        onChange={onChange}
      />,
    );
    fireEvent.click(view.getByRole('switch'));
    expect(onChange).toHaveBeenCalledWith({ [FILTER_ID]: true });
  });

  it('keeps a disabled canvas filter from being toggled', () => {
    const onChange = vi.fn();
    const view = render(
      <Panel
        definitions={disabledDefinitions}
        dataSourceParams={params}
        filterBindings={{ [FILTER_ID]: true }}
        onChange={onChange}
      />,
    );
    const toggle = view.getByRole('switch');
    expect(toggle.hasAttribute('disabled') || toggle.getAttribute('aria-disabled') === 'true').toBe(true);
    fireEvent.click(toggle);
    expect(onChange).not.toHaveBeenCalled();
  });
});
