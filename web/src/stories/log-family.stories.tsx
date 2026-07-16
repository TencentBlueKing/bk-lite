import type { Meta, StoryObj } from '@storybook/react';
import IntroRenderer from '@/app/log/(pages)/integration/list/detail/output/introRenderer';
import GuideStepPanel from '@/components/guide-step-panel';
import LogDonutChart from '@/components/log-donut-chart';
import LogKpiCard, {
  type LogKpiCardCalculateMetric,
} from '@/components/log-kpi-card';
import SectionHeader from '@/components/section-header';

const timeseriesRows = [
  { _time: '2026-06-25T08:00:00.000Z', total_count: 180, err_count: 8, latency_ms: 126 },
  { _time: '2026-06-25T08:05:00.000Z', total_count: 220, err_count: 11, latency_ms: 132 },
  { _time: '2026-06-25T08:10:00.000Z', total_count: 205, err_count: 9, latency_ms: 121 },
  { _time: '2026-06-25T08:15:00.000Z', total_count: 268, err_count: 14, latency_ms: 147 },
];

const previousRows = [
  { _time: '2026-06-25T07:40:00.000Z', total_count: 160, err_count: 6, latency_ms: 118 },
  { _time: '2026-06-25T07:45:00.000Z', total_count: 174, err_count: 7, latency_ms: 120 },
  { _time: '2026-06-25T07:50:00.000Z', total_count: 182, err_count: 8, latency_ms: 123 },
  { _time: '2026-06-25T07:55:00.000Z', total_count: 196, err_count: 9, latency_ms: 128 },
];

const normalizeMultiQueryData = (data: any): any[] => {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== 'object') return [];

  const timeMap = new Map<string, Record<string, unknown>>();
  for (const key of Object.keys(data)) {
    const rows = data[key];
    if (!Array.isArray(rows)) continue;

    for (const row of rows) {
      const time = String(row._time ?? '');
      if (!timeMap.has(time)) {
        timeMap.set(time, { _time: time });
      }

      const merged = timeMap.get(time)!;
      for (const [field, value] of Object.entries(row)) {
        if (field !== '_time') {
          merged[field] = value;
        }
      }
    }
  }

  return Array.from(timeMap.values()).sort((a, b) =>
    String(a._time).localeCompare(String(b._time))
  );
};

const toNumber = (value: unknown) => {
  const parsed = Number.parseFloat(String(value ?? 0));
  return Number.isNaN(parsed) ? 0 : parsed;
};

const ratioMetric: LogKpiCardCalculateMetric = (rawData, prevData, config) => {
  const currentRows = normalizeMultiQueryData(rawData);
  const previousTrendRows = normalizeMultiQueryData(prevData);
  const numeratorField = config?.numeratorField;
  const denominatorField = config?.denominatorField;

  const toRatioSeries = (rows: any[]) =>
    rows.map((row) => {
      const denominator = toNumber(row[denominatorField]);
      return denominator > 0
        ? (toNumber(row[numeratorField]) / denominator) * 100
        : 0;
    });

  const trendData = toRatioSeries(currentRows);
  const previousTrendData = toRatioSeries(previousTrendRows);
  const currentValue = trendData.length
    ? trendData.reduce((sum, value) => sum + value, 0) / trendData.length
    : undefined;
  const previousValue = previousTrendData.length
    ? previousTrendData.reduce((sum, value) => sum + value, 0) / previousTrendData.length
    : undefined;

  let changePercent: number | null = null;
  if (typeof currentValue === 'number' && typeof previousValue === 'number') {
    if (previousValue !== 0) {
      changePercent = ((currentValue - previousValue) / previousValue) * 100;
    } else if (currentValue > 0) {
      changePercent = 100;
    }
  }

  return {
    currentValue,
    changePercent,
    trendData,
  };
};

const FamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="Dashboard summary widgets"
          description="Shared KPI and donut widgets power multiple log-analysis dashboards while keeping summary semantics stable across protocol-specific views. Their governed Storybook contract now lives under a dedicated `Business/Log/Summary/*` subtree beside the analysis widget family."
        />

        <div className="grid gap-4 xl:grid-cols-[360px_420px]">
          <div style={{ height: 220, width: 360, padding: 16, background: 'var(--color-bg-2)' }}>
            <LogKpiCard
              rawData={timeseriesRows}
              prevData={previousRows}
              config={{
                displayMaps: { value: 'total_count' },
                color: 'primary',
              }}
            />
          </div>

          <div style={{ height: 280, width: 420, padding: 16, background: 'var(--color-bg-2)' }}>
            <LogDonutChart
              rawData={[
                { name: 'Error', count: 148 },
                { name: 'Warning', count: 96 },
                { name: 'Info', count: 312 },
                { name: 'Debug', count: 44 },
              ]}
              config={{
                displayMaps: {
                  key: 'name',
                  value: 'count',
                },
              }}
            />
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[360px_420px]">
          <div style={{ height: 220, width: 360, padding: 16, background: 'var(--color-bg-2)' }}>
            <LogKpiCard
              rawData={timeseriesRows}
              prevData={previousRows}
              config={{
                displayMaps: { value: 'latency_ms' },
                metricMode: 'latest',
                color: 'warning',
                valueFormatter: (value: number) => `${value.toFixed(0)} ms`,
              }}
            />
          </div>

          <div style={{ height: 280, width: 420, padding: 16, background: 'var(--color-bg-2)' }}>
            <LogDonutChart
              rawData={[
                { level: 'ERROR', cnt: 88 },
                { level: 'WARN', cnt: 64 },
                { level: 'INFO', cnt: 201 },
                { level: 'DEBUG', cnt: 35 },
              ]}
              config={{
                displayMaps: {
                  key: 'level',
                  value: 'cnt',
                },
              }}
            />
          </div>
        </div>

        <div style={{ height: 280, width: 420, padding: 16, background: 'var(--color-bg-2)' }}>
          <LogDonutChart
            rawData={[
              { bucket: 'Authentication failure from unknown source', count: 52 },
              { bucket: 'Cluster or type mismatch', count: 39 },
              { bucket: 'Command execution log', count: 118 },
              { bucket: 'Other events', count: 21 },
            ]}
            config={{
              displayMaps: {
                key: 'bucket',
                value: 'count',
              },
            }}
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="Derived metric behavior"
          description="Log KPI cards also support multi-query derived metrics, which is a stable contract for HTTP and service-specific error-rate dashboards."
        />

        <div style={{ height: 220, width: 360, padding: 16, background: 'var(--color-bg-2)' }}>
          <LogKpiCard
            rawData={{
              requests: [
                { _time: '2026-06-25T08:00:00.000Z', reqcount: 180 },
                { _time: '2026-06-25T08:05:00.000Z', reqcount: 220 },
                { _time: '2026-06-25T08:10:00.000Z', reqcount: 205 },
                { _time: '2026-06-25T08:15:00.000Z', reqcount: 268 },
              ],
              errors: [
                { _time: '2026-06-25T08:00:00.000Z', errcount: 8 },
                { _time: '2026-06-25T08:05:00.000Z', errcount: 11 },
                { _time: '2026-06-25T08:10:00.000Z', errcount: 9 },
                { _time: '2026-06-25T08:15:00.000Z', errcount: 14 },
              ],
            }}
            prevData={{
              requests: [
                { _time: '2026-06-25T07:40:00.000Z', reqcount: 160 },
                { _time: '2026-06-25T07:45:00.000Z', reqcount: 174 },
                { _time: '2026-06-25T07:50:00.000Z', reqcount: 182 },
                { _time: '2026-06-25T07:55:00.000Z', reqcount: 196 },
              ],
              errors: [
                { _time: '2026-06-25T07:40:00.000Z', errcount: 6 },
                { _time: '2026-06-25T07:45:00.000Z', errcount: 7 },
                { _time: '2026-06-25T07:50:00.000Z', errcount: 8 },
                { _time: '2026-06-25T07:55:00.000Z', errcount: 9 },
              ],
            }}
            calculateMetric={ratioMetric}
            config={{
              numeratorField: 'errcount',
              denominatorField: 'reqcount',
              color: 'danger',
              valueFormatter: (value: number) => `${value.toFixed(1)}%`,
            }}
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="Introduction step contract"
          description="Log integration introduction pages now share the governed ordered-instruction shell for deployment and verification steps instead of keeping a page-local numbered media block inside the intro renderer."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <IntroRenderer
            config={{
              overview: {
                title: 'File collection overview',
                paragraphs: [
                  'Use this integration to tail application logs and normalize fields before indexing.',
                ],
              },
              steps: {
                title: 'Deployment steps',
                description:
                  'The log integration guide now shares the governed ordered-instruction shell used by other onboarding and operations flows.',
                items: [
                  {
                    title: 'Install the collector',
                    description:
                      'Install the log collector on the target host and confirm the service starts successfully.',
                    code: 'curl -fsSL https://bk-lite.example.com/install-log-agent.sh | bash',
                  },
                  {
                    title: 'Configure the source path',
                    description:
                      'Point the collector at `/var/log/app.log` and keep the instance label aligned with the monitored asset.',
                  },
                  {
                    title: 'Verify ingestion',
                    description:
                      'Generate sample traffic, then confirm new log lines appear in the BK-Lite log index.',
                  },
                ],
              },
              tips: [
                {
                  type: 'info',
                  title: 'Collector note',
                  content: 'Use `root` or a service account with read access to the target log files.',
                },
              ],
            }}
          />
        </div>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <div className="space-y-3">
            {[
              'Install the collector on the target host.',
              'Configure the source path and labels for the log file.',
              'Generate sample traffic and verify new events are indexed.',
            ].map((item, index) => (
              <GuideStepPanel
                key={item}
                step={index + 1}
                title={item}
                spacing="flush"
              >
                {null}
              </GuideStepPanel>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/Log/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 940, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
