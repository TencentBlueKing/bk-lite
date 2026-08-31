import { afterEach, describe, expect, it } from 'vitest';

import {
  buildDashboardCaption,
  buildDashboardCurrentTime,
  getTextContext,
  isDecorativeDashboardChart,
  labelFromDashboardCard,
  readDashboardKpiReadings,
  readDashboardPageDataStamp,
} from '../dashboard.pilot';

describe('dashboard.pilot chart labeling', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('skips KPI mini sparklines and reads the ring card title', () => {
    document.body.innerHTML = `
      <section>
        <div class="statCard">
          <div class="statLabel"><span class="titleWithGuide"><span>CPU 使用率</span></span></div>
          <div class="miniTrend"><div _echarts_instance_="kpi" style="height:40px"></div></div>
        </div>
        <div class="panel">
          <h3 class="panelTitle"><span class="titleWithGuide"><span>CPU 时间分布</span></span></h3>
          <div class="metricRow">
            <span class="metricName">用户态</span>
            <span class="metricPercent">76.4%</span>
            <span class="metricCount">(21.8%)</span>
          </div>
          <div class="metricRow">
            <span class="metricName">内核态</span>
            <span class="metricPercent">0.0%</span>
            <span class="metricCount">(--)</span>
          </div>
          <div _echarts_instance_="ring"></div>
        </div>
      </section>
    `;
    const kpi = document.querySelector<HTMLElement>('[_echarts_instance_="kpi"]');
    const ring = document.querySelector<HTMLElement>('[_echarts_instance_="ring"]');
    expect(kpi && isDecorativeDashboardChart(kpi)).toBe(true);
    expect(ring && isDecorativeDashboardChart(ring)).toBe(false);
    expect(ring && labelFromDashboardCard(ring)).toEqual({
      title: 'CPU 时间分布',
      legends: ['用户态 76.4% (21.8%)', '内核态 0.0% (--)'],
      readings: ['用户态 76.4% (21.8%)', '内核态 0.0% (--)'],
    });
  });

  it('uses visible ring readings instead of raw echarts precision', () => {
    const caption = buildDashboardCaption(
      { caption: '图表；序列: 用户态, 内核态；最新值: 21.759, 3.165', dataUrl: 'data:x' },
      {
        title: 'CPU 时间分布',
        legends: ['用户态 76.4% (21.8%)', '内核态 0.0% (--)'],
        readings: ['用户态 76.4% (21.8%)', '内核态 0.0% (--)'],
      },
    );
    expect(caption).toBe('CPU 时间分布；序列: 用户态 76.4% (21.8%), 内核态 0.0% (--)');
    expect(caption).not.toContain('21.759');
  });
});

describe('dashboard.pilot page data stamp', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('builds currentTime from time filter and KPI fingerprint', () => {
    document.body.innerHTML = `
      <div class="toolbarTimeSelector">
        <div class="ant-select-selection-item">最近6小时</div>
      </div>
      <div class="statCard"><div class="statValue">86.2%</div></div>
      <div class="statCard"><div class="statValue">79.1%</div></div>
      <div class="collectionStatusValue">正常</div>
      <div class="uptimeStatusMain">运行正常</div>
    `;
    const stamp = readDashboardPageDataStamp();
    expect(stamp.timeRangeLabel).toBe('最近6小时');
    expect(stamp.kpiFingerprint).toBe('86.2%|79.1%');
    expect(stamp.kpiReadings).toEqual([]);
    expect(buildDashboardCurrentTime(stamp)).toBe('最近6小时::86.2%|79.1%::正常::运行正常');
  });

  it('reads labeled KPI values from stat cards', () => {
    document.body.innerHTML = `
      <div class="statCard">
        <div class="statLabel"><span class="titleWithGuide"><span>磁盘使用率</span></span></div>
        <div class="statValue">82.9%</div>
      </div>
      <div class="statCard">
        <div class="statLabel"><span class="titleWithGuide"><span>CPU 使用率</span></span></div>
        <div class="statValue">86.0%</div>
      </div>
    `;
    expect(readDashboardKpiReadings()).toEqual(['磁盘使用率: 82.9%', 'CPU 使用率: 86.0%']);
    expect(getTextContext().sections?.some((section) => section.content.includes('磁盘使用率: 82.9%'))).toBe(true);
  });

  it('changes currentTime when time filter label changes', () => {
    document.body.innerHTML = `
      <div class="toolbarTimeSelector">
        <div class="ant-select-selection-item">最近15分钟</div>
      </div>
      <div class="statCard"><div class="statValue">22.4%</div></div>
    `;
    const stamp15 = readDashboardPageDataStamp();
    document.querySelector('.ant-select-selection-item')!.textContent = '最近6小时';
    document.querySelector('.statValue')!.textContent = '86.0%';
    const stamp6h = readDashboardPageDataStamp();
    expect(buildDashboardCurrentTime(stamp15)).not.toBe(buildDashboardCurrentTime(stamp6h));
  });
});
