import React from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';

interface Point {
  t: number;
  read: number;
  write: number;
  latency: number;
}

interface StoragePreviewData {
  vendor: 'Pure FlashArray' | 'InfiniBox';
  instance: string;
  totalBytes: number;
  usedBytes: number;
  readIops: number;
  writeIops: number;
  readBandwidth: number;
  writeBandwidth: number;
  readLatency: number;
  writeLatency: number;
  volumeCount: number;
  poolCount?: number;
  extensionLabel: string;
  extensionValue: string;
  series: Point[];
  resources: Array<{ name: string; type: string; used: number; iops: number; latency: number }>;
}

const teb = 1024 ** 4;
const gib = 1024 ** 3;

const formatBytes = (value: number) => {
  if (value >= teb) return `${(value / teb).toFixed(1)} TiB`;
  return `${(value / gib).toFixed(0)} GiB`;
};

const formatRate = (value: number) => `${(value / gib).toFixed(1)} GiB/s`;

const buildSeries = (seed: number): Point[] =>
  Array.from({ length: 36 }, (_, index) => {
    const wave = Math.sin(index / 3 + seed);
    const pulse = index % 11 === 0 ? 1.35 : 1;
    return {
      t: index,
      read: Math.round((52000 + wave * 9000 + index * 190) * pulse),
      write: Math.round((31000 + Math.cos(index / 4 + seed) * 6000 + index * 140) * pulse),
      latency: Number((1.2 + Math.max(0, wave) * 0.8 + (pulse - 1) * 1.2).toFixed(2))
    };
  });

const PURE_DATA: StoragePreviewData = {
  vendor: 'Pure FlashArray',
  instance: 'local_storage_pure_flasharray_01',
  totalBytes: 268 * teb,
  usedBytes: 163 * teb,
  readIops: 78400,
  writeIops: 42100,
  readBandwidth: 7.8 * gib,
  writeBandwidth: 4.1 * gib,
  readLatency: 1.4,
  writeLatency: 1.9,
  volumeCount: 128,
  extensionLabel: '数据缩减率',
  extensionValue: '4.8:1',
  series: buildSeries(0.4),
  resources: [
    { name: 'ora-prod-data', type: 'volume', used: 82, iops: 24200, latency: 1.5 },
    { name: 'vmware-gold', type: 'volume', used: 71, iops: 18100, latency: 1.2 },
    { name: 'bk-lite-metrics', type: 'volume', used: 54, iops: 9800, latency: 0.9 }
  ]
};

const INFINIBOX_DATA: StoragePreviewData = {
  vendor: 'InfiniBox',
  instance: 'local_storage_infinibox_01',
  totalBytes: 512 * teb,
  usedBytes: 337 * teb,
  readIops: 63800,
  writeIops: 37700,
  readBandwidth: 6.2 * gib,
  writeBandwidth: 3.9 * gib,
  readLatency: 2.1,
  writeLatency: 2.7,
  volumeCount: 214,
  poolCount: 2,
  extensionLabel: '虚拟容量',
  extensionValue: '1.2 PiB',
  series: buildSeries(1.5),
  resources: [
    { name: 'pool-a', type: 'pool', used: 76, iops: 38600, latency: 2.2 },
    { name: 'pool-b', type: 'pool', used: 58, iops: 24800, latency: 1.9 },
    { name: 'sap-hana-logs', type: 'volume', used: 69, iops: 14200, latency: 2.6 }
  ]
};

const linePath = (values: number[], width = 520, height = 120) => {
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = Math.max(max - min, 1);
  return values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * width;
      const y = height - ((value - min) / span) * (height - 18) - 9;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
};

const Stat = ({ label, value, unit, tone }: { label: string; value: string; unit?: string; tone: string }) => (
  <div style={styles.statCard}>
    <div style={styles.statLabel}>{label}</div>
    <div style={{ ...styles.statValue, color: tone }}>{value}<span style={styles.unit}>{unit}</span></div>
    <div style={styles.spark}><span style={{ ...styles.sparkFill, background: tone }} /></div>
  </div>
);

function StorageDashboardPreview({ data }: { data: StoragePreviewData }) {
  const usedPercent = Math.round((data.usedBytes / data.totalBytes) * 100);
  return (
    <div style={styles.page}>
      <div style={styles.shell}>
        <div style={styles.header}>
          <div>
            <div style={styles.eyebrow}>Storage dashboard</div>
            <h1 style={styles.title}>存储监控仪表盘</h1>
            <div style={styles.meta}>{data.vendor} · {data.instance} · Asia/Shanghai</div>
          </div>
          <div style={styles.badge}>采集正常</div>
        </div>

        <div style={styles.statGrid}>
          <Stat label="容量使用率" value={`${usedPercent}`} unit="%" tone="#fa8c16" />
          <Stat label="总容量" value={formatBytes(data.totalBytes)} tone="#2f6bff" />
          <Stat label="读 IOPS" value={data.readIops.toLocaleString()} tone="#2f6bff" />
          <Stat label="读吞吐" value={formatRate(data.readBandwidth)} tone="#27c274" />
          <Stat label="读延迟" value={data.readLatency.toFixed(1)} unit="ms" tone="#ff4d4f" />
          <Stat label={data.extensionLabel} value={data.extensionValue} tone="#722ed1" />
        </div>

        <div style={styles.grid}>
          <section style={styles.panel}>
            <div style={styles.panelTitle}>容量分布</div>
            <div style={styles.capacityWrap}>
              <div
                style={{
                  ...styles.ring,
                  background: `conic-gradient(#fa8c16 ${usedPercent}%, #27c274 0)`
                }}
              >
                <div style={styles.ringCenter}>
                  <strong>{usedPercent}%</strong>
                  <span>使用率</span>
                </div>
              </div>
              <div style={styles.capacityList}>
                <div style={styles.capacityItem}><b style={styles.capacityLabel}>已用</b><span style={styles.capacityValue}>{formatBytes(data.usedBytes)}</span></div>
                <div style={styles.capacityItem}><b style={styles.capacityLabel}>可用</b><span style={styles.capacityValue}>{formatBytes(data.totalBytes - data.usedBytes)}</span></div>
                <div style={styles.capacityItem}><b style={styles.capacityLabel}>卷数量</b><span style={styles.capacityValue}>{data.volumeCount}</span></div>
                {data.poolCount ? <div style={styles.capacityItem}><b style={styles.capacityLabel}>Pool</b><span style={styles.capacityValue}>{data.poolCount}</span></div> : null}
              </div>
            </div>
          </section>

          <section style={{ ...styles.panel, gridColumn: 'span 2' }}>
            <div style={styles.panelTitle}>IOPS 与延迟趋势</div>
            <svg viewBox="0 0 520 140" style={styles.chart}>
              <path d={linePath(data.series.map((p) => p.read))} fill="none" stroke="#2f6bff" strokeWidth="3" />
              <path d={linePath(data.series.map((p) => p.write))} fill="none" stroke="#13c2c2" strokeWidth="3" />
              <path d={linePath(data.series.map((p) => p.latency * 22000))} fill="none" stroke="#ff4d4f" strokeWidth="2" opacity="0.75" />
            </svg>
            <div style={styles.legend}>
              <span><i style={{ background: '#2f6bff' }} />读 IOPS</span>
              <span><i style={{ background: '#13c2c2' }} />写 IOPS</span>
              <span><i style={{ background: '#ff4d4f' }} />延迟</span>
            </div>
          </section>
        </div>

        <section style={styles.panel}>
          <div style={styles.panelTitle}>资源诊断</div>
          <div style={styles.table}>
            {data.resources.map((item) => (
              <div key={item.name} style={styles.row}>
                <span>{item.name}<em>{item.type}</em></span>
                <span>{item.used}% used</span>
                <span>{item.iops.toLocaleString()} IOPS</span>
                <span>{item.latency.toFixed(1)} ms</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: { minHeight: '100vh', background: '#f5f7fb', padding: 24, color: '#1f2430' },
  shell: { maxWidth: 1320, margin: '0 auto', display: 'grid', gap: 16 },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  eyebrow: { color: '#667085', fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' },
  title: { margin: '4px 0', fontSize: 28, lineHeight: 1.2 },
  meta: { color: '#667085', fontSize: 13 },
  badge: { padding: '7px 12px', borderRadius: 6, background: '#e8f7ef', color: '#16894c', fontWeight: 700 },
  statGrid: { display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: 12 },
  statCard: { background: '#fff', border: '1px solid #e6eaf2', borderRadius: 8, padding: 14, minHeight: 112 },
  statLabel: { color: '#667085', fontSize: 13, marginBottom: 10 },
  statValue: { fontSize: 24, fontWeight: 800, whiteSpace: 'nowrap' },
  unit: { fontSize: 13, marginLeft: 4, color: '#667085' },
  spark: { height: 4, background: '#eef2f7', borderRadius: 999, marginTop: 18, overflow: 'hidden' },
  sparkFill: { display: 'block', height: '100%', width: '68%', opacity: 0.85 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16 },
  panel: { background: '#fff', border: '1px solid #e6eaf2', borderRadius: 8, padding: 16 },
  panelTitle: { fontSize: 15, fontWeight: 800, marginBottom: 14 },
  capacityWrap: { display: 'grid', gridTemplateColumns: '170px 1fr', gap: 18, alignItems: 'center' },
  ring: { width: 156, height: 156, borderRadius: '50%', display: 'grid', placeItems: 'center' },
  ringCenter: { width: 104, height: 104, borderRadius: '50%', background: '#fff', display: 'grid', placeItems: 'center', alignContent: 'center' },
  capacityList: { display: 'grid', gap: 10 },
  capacityItem: { display: 'grid', gridTemplateColumns: '58px auto', columnGap: 12, alignItems: 'baseline', justifyContent: 'start', fontSize: 16 },
  capacityLabel: { color: '#1f2430', whiteSpace: 'nowrap' },
  capacityValue: { fontWeight: 800, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' },
  chart: { width: '100%', height: 154, background: 'linear-gradient(#fff, #fbfcff)' },
  legend: { display: 'flex', gap: 18, color: '#667085', fontSize: 12 },
  table: { display: 'grid', gap: 8 },
  row: { display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr', gap: 12, padding: '10px 0', borderTop: '1px solid #edf0f5', alignItems: 'center' }
};

const meta: Meta<typeof StorageDashboardPreview> = {
  title: 'Monitor/Dashboard/Storage',
  component: StorageDashboardPreview,
  parameters: { layout: 'fullscreen' }
};

export default meta;

type Story = StoryObj<typeof StorageDashboardPreview>;

export const PureFlashArray: Story = {
  name: 'Pure FlashArray',
  args: { data: PURE_DATA }
};

export const InfiniBox: Story = {
  args: { data: INFINIBOX_DATA }
};
