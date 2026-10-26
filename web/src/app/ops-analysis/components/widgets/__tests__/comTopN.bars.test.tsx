import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import React from 'react';
import { IntlProvider } from 'react-intl';
import ComTopN from '../comTopN';

afterEach(cleanup);

const renderTopN = (node: React.ReactNode) => render(
  <IntlProvider locale="zh" messages={{}}>
    {node}
  </IntlProvider>,
);

const barWidths = () => Array.from(document.querySelectorAll<HTMLElement>('.rounded-full.transition-all'))
  .map((node) => node.style.width);

describe('ComTopN bar scale', () => {
  it('keeps relative widths for array rankings', () => {
    renderTopN(
      <ComTopN
        rawData={[
          { name: '低', value: 10 },
          { name: '高', value: 40 },
        ]}
        config={{ chartType: 'topN', topNLabelField: 'name', topNValueField: 'value' }}
      />,
    );

    expect(screen.getByText('高')).toBeTruthy();
    expect(screen.getByText('低')).toBeTruthy();
    expect(barWidths()).toEqual(['100%', '25%']);
  });

  it('draws scalar rows in configured order on a fixed full score', () => {
    renderTopN(
      <ComTopN
        rawData={{ avg_disk: 80, avg_cpu: 25, avg_memory: 150 }}
        config={{
          chartType: 'topN',
          barMode: 'absolute',
          barMax: 100,
          unitId: 'percent',
          topNScalarFields: [
            { field: 'avg_cpu', label: 'CPU 使用率' },
            { field: 'avg_memory', label: '内存使用率' },
            { field: 'avg_disk', label: '磁盘使用率' },
          ],
        }}
      />,
    );

    const names = screen.getAllByText(/使用率/).map((node) => node.textContent);
    expect(names).toEqual(['CPU 使用率', '内存使用率', '磁盘使用率']);
    expect(barWidths()).toEqual(['25%', '100%', '80%']);
  });

  it('floors only relative bars below two percent', () => {
    renderTopN(
      <ComTopN
        rawData={[
          { name: '高', value: 100 },
          { name: '低', value: 1 },
        ]}
        config={{ chartType: 'topN', topNLabelField: 'name', topNValueField: 'value' }}
      />,
    );
    expect(barWidths()).toEqual(['100%', '2%']);
  });

  it('keeps an absolute bar at its exact percent', () => {
    renderTopN(
      <ComTopN
        rawData={{ tiny: 1 }}
        config={{
          chartType: 'topN',
          barMode: 'absolute',
          barMax: 100,
          topNScalarFields: [{ field: 'tiny', label: '微量' }],
        }}
      />,
    );
    expect(barWidths()).toEqual(['1%']);
  });
});
