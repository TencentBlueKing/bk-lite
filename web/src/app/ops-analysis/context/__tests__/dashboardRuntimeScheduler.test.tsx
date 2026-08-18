// @vitest-environment jsdom

import React, { StrictMode, useEffect } from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  DashboardRuntimeSchedulerProvider,
  useDashboardRuntimeScheduler,
} from '@/app/ops-analysis/context/dashboardRuntimeScheduler';

afterEach(cleanup);

describe('DashboardRuntimeSchedulerProvider', () => {
  it('survives React StrictMode effect replay', async () => {
    const start = vi.fn(async () => 'ok');
    const settled = vi.fn();
    let consumerSequence = 0;
    const Probe = () => {
      const scheduler = useDashboardRuntimeScheduler();
      useEffect(() => {
        void scheduler?.schedule({
          consumerId: `consumer-${++consumerSequence}`,
          ownerId: 'widget',
          physicalKey: 'same-request',
          priority: { cause: 1, visibility: 0, distance: 0, order: 0 },
          start,
        }).then(settled);
      }, [scheduler]);
      return null;
    };

    render(
      <StrictMode>
        <DashboardRuntimeSchedulerProvider>
          <Probe />
        </DashboardRuntimeSchedulerProvider>
      </StrictMode>,
    );

    await waitFor(() => expect(settled).toHaveBeenCalled());
    expect(start).toHaveBeenCalledTimes(1);
  });
});
