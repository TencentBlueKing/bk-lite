import React, { useEffect, useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import EffectiveTime, { EffectiveTimeValue } from '../effectiveTime';
import AlarmEffectiveTime from '@/app/alarm/components/alarm-effective-time';

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
});

afterEach(cleanup);

const hydratedWeek: EffectiveTimeValue = {
  type: 'week',
  week_month: [6],
  start_time: '14:00:00',
  end_time: '16:00:00',
};

function HydrateHarness({
  Component,
}: {
  Component: React.ComponentType<{
    open: boolean;
    value?: EffectiveTimeValue;
    onChange?: (value: EffectiveTimeValue) => void;
  }>;
}) {
  const [value, setValue] = useState<EffectiveTimeValue | undefined>(undefined);
  useEffect(() => {
    setValue(hydratedWeek);
  }, []);
  return (
    <>
      <Component open value={value} onChange={setValue} />
      <pre data-testid="current-value">{JSON.stringify(value)}</pre>
    </>
  );
}

describe.each([
  ['settings EffectiveTime', EffectiveTime],
  ['alarm EffectiveTime', AlarmEffectiveTime],
])('%s 回填不冲时段', (_, Component) => {
  it('默认值之后写入每周 14:00-16:00 时保留原时段', async () => {
    render(<HydrateHarness Component={Component} />);

    await waitFor(() => {
      expect(screen.getByTestId('current-value').textContent).toContain('"start_time":"14:00:00"');
    });
    expect(screen.getByTestId('current-value').textContent).toContain('"end_time":"16:00:00"');
    expect(screen.getByTestId('current-value').textContent).toContain('"type":"week"');
  });

  it('用户切换类型时才重置为默认时段', async () => {
    const onChange = vi.fn();
    render(<Component open value={hydratedWeek} onChange={onChange} />);

    fireEvent.mouseDown(screen.getAllByRole('combobox')[0]);
    fireEvent.click(await screen.findByTitle('每天'));

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'day',
          start_time: '00:00:00',
          end_time: '23:59:59',
        }),
      );
    });
  });
});
