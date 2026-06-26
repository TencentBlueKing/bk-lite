'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Spin, Tooltip, Drawer, Button, Tag, Empty } from 'antd';
import { ArrowLeftOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi } from '@/app/cmdb/api/instance';
import { useRouter } from 'next/navigation';

// ─── Types ────────────────────────────────────────────────────────────────────

interface IpInstance {
  _id: number | string;
  ip_addr: string;
  ip_status?: string[];
  ip_allocated_status?: string[];
  inst_name?: string;
  [key: string]: unknown;
}

interface IpamViewData {
  subnet_address: string;
  subnet_mask: string;
  prefixlen: number;
  capacity: number;
  used: number;
  available: number;
  ratio: number;
  status_counts: Record<string, number>;
  ips: IpInstance[];
}

// ─── Color / Status mapping ───────────────────────────────────────────────────

// Cell kind (determines color)
type CellKind =
  | 'free'
  | 'allocated_online'
  | 'allocated_offline'
  | 'conflict'
  | 'reserved'
  | 'gateway'
  | 'unknown';

const KIND_COLOR: Record<CellKind, string> = {
  free: '#52c41a',
  allocated_online: '#1677ff',
  allocated_offline: '#8c8c8c',
  conflict: '#ff4d4f',
  reserved: '#faad14',
  gateway: '#722ed1',
  unknown: '#bfbfbf',
};

function ipToCellKind(ip: IpInstance): CellKind {
  const statuses = ip.ip_status ?? [];
  const allocStatuses = ip.ip_allocated_status ?? [];
  const ipType = ip.ip_type
    ? Array.isArray(ip.ip_type)
      ? (ip.ip_type as string[])
      : [String(ip.ip_type)]
    : [];

  if (statuses.includes('conflict')) return 'conflict';
  if (allocStatuses.includes('reserved')) return 'reserved';
  if (ipType.includes('gateway')) return 'gateway';

  const isOnline = statuses.includes('online');
  const isOffline = statuses.includes('offline');
  const isAllocated = allocStatuses.includes('allocated');

  if (isAllocated && isOnline) return 'allocated_online';
  if (isAllocated && isOffline) return 'allocated_offline';
  if (isAllocated) return 'allocated_online'; // fallback

  if (statuses.includes('unknown') || allocStatuses.includes('unknown')) return 'unknown';

  return 'unknown';
}

// Extract host octet (last segment) from an IP addr string
function hostOctet(ipAddr: string): number {
  const parts = ipAddr.split('.');
  return parseInt(parts[parts.length - 1], 10);
}

// Build octet → ip map from stored ips
function buildOctetMap(ips: IpInstance[]): Map<number, IpInstance> {
  const m = new Map<number, IpInstance>();
  for (const ip of ips) {
    const oct = hostOctet(ip.ip_addr);
    if (!isNaN(oct)) m.set(oct, ip);
  }
  return m;
}

// ─── Summary bar ─────────────────────────────────────────────────────────────

interface SummaryBarProps {
  data: IpamViewData;
}

const SummaryBar: React.FC<SummaryBarProps> = ({ data }) => {
  const { t } = useTranslation();
  const pct = Math.round(data.ratio * 100);
  return (
    <div style={{ display: 'flex', gap: 24, alignItems: 'center', padding: '8px 0 12px', flexWrap: 'wrap' }}>
      <span style={{ color: 'var(--color-text-3)', fontSize: 13 }}>
        {data.subnet_address}/{data.prefixlen}
      </span>
      <span>
        <span style={{ color: 'var(--color-text-3)', fontSize: 12, marginRight: 4 }}>{t('Model.ipViewCapacity')}:</span>
        <strong>{data.capacity}</strong>
      </span>
      <span>
        <span style={{ color: 'var(--color-text-3)', fontSize: 12, marginRight: 4 }}>{t('Model.ipViewUsed')}:</span>
        <strong style={{ color: '#1677ff' }}>{data.used}</strong>
      </span>
      <span>
        <span style={{ color: 'var(--color-text-3)', fontSize: 12, marginRight: 4 }}>{t('Model.ipViewAvailable')}:</span>
        <strong style={{ color: '#52c41a' }}>{data.available}</strong>
      </span>
      <span>
        <span style={{ color: 'var(--color-text-3)', fontSize: 12, marginRight: 4 }}>{t('Model.ipViewRatio')}:</span>
        <strong style={{ color: pct > 80 ? '#ff4d4f' : '#1677ff' }}>{pct}%</strong>
      </span>
      <div style={{ flexBasis: '100%', height: 6, background: 'var(--color-fill-2)', borderRadius: 3, overflow: 'hidden', marginTop: 2 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: pct > 80 ? '#ff4d4f' : '#1677ff', transition: 'width .3s' }} />
      </div>
    </div>
  );
};

// ─── Legend ──────────────────────────────────────────────────────────────────

const Legend: React.FC = () => {
  const { t } = useTranslation();
  const items: Array<{ kind: CellKind; label: string }> = [
    { kind: 'free', label: t('Model.ipViewFree') },
    { kind: 'allocated_online', label: t('Model.ipViewAllocatedOnline') },
    { kind: 'allocated_offline', label: t('Model.ipViewAllocatedOffline') },
    { kind: 'conflict', label: t('Model.ipViewConflict') },
    { kind: 'reserved', label: t('Model.ipViewReserved') },
    { kind: 'gateway', label: t('Model.ipViewGateway') },
    { kind: 'unknown', label: t('Model.ipViewUnknown') },
  ];
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 20px', padding: '8px 0' }}>
      {items.map(({ kind, label }) => (
        <span key={kind} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
          <span
            style={{
              width: 14, height: 14, borderRadius: 3,
              background: KIND_COLOR[kind], display: 'inline-block', flexShrink: 0,
            }}
          />
          <span style={{ color: 'var(--color-text-2)' }}>{label}</span>
        </span>
      ))}
    </div>
  );
};

// ─── IP Detail Drawer ─────────────────────────────────────────────────────────

interface IpDetailDrawerProps {
  ip: IpInstance | null;
  open: boolean;
  onClose: () => void;
}

const IpDetailDrawer: React.FC<IpDetailDrawerProps> = ({ ip, open, onClose }) => {
  const { t } = useTranslation();
  const router = useRouter();

  const jump = useCallback(() => {
    if (!ip) return;
    const params = new URLSearchParams({
      icn: '',
      model_name: 'ip',
      model_id: 'ip',
      classification_id: '',
      inst_id: String(ip._id),
      inst_name: ip.ip_addr,
    }).toString();
    router.push(`/cmdb/assetData/detail/baseInfo?${params}`);
  }, [ip, router]);

  if (!ip) return null;

  const kind = ipToCellKind(ip);
  const color = KIND_COLOR[kind];
  const kindLabel: Record<CellKind, string> = {
    free: t('Model.ipViewFree'),
    allocated_online: t('Model.ipViewAllocatedOnline'),
    allocated_offline: t('Model.ipViewAllocatedOffline'),
    conflict: t('Model.ipViewConflict'),
    reserved: t('Model.ipViewReserved'),
    gateway: t('Model.ipViewGateway'),
    unknown: t('Model.ipViewUnknown'),
  };

  const rows: Array<{ k: string; v: string }> = [];
  for (const [key, val] of Object.entries(ip)) {
    if (key === '_id' || key === 'inst_name') continue;
    if (val === null || val === undefined || val === '') continue;
    const display = Array.isArray(val) ? val.join(', ') : String(val);
    if (display === '') continue;
    rows.push({ k: key, v: display });
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={360}
      title={
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span
            style={{
              width: 10, height: 10, borderRadius: '50%',
              background: color, boxShadow: `0 0 8px ${color}`, display: 'inline-block',
            }}
          />
          {ip.ip_addr}
        </span>
      }
      extra={
        <Button size="small" icon={<ArrowRightOutlined />} onClick={jump}>
          {t('Model.viewFullInstance')}
        </Button>
      }
    >
      <div style={{ marginBottom: 12 }}>
        <Tag color={color} style={{ color: '#fff' }}>{kindLabel[kind]}</Tag>
      </div>
      <div>
        {rows.map(({ k, v }) => (
          <div
            key={k}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              padding: '8px 0',
              borderBottom: '1px dashed var(--color-border-2)',
              gap: 12,
            }}
          >
            <span style={{ color: 'var(--color-text-3)', fontSize: 13, flexShrink: 0 }}>{k}</span>
            <span
              style={{
                fontSize: 13, textAlign: 'right', wordBreak: 'break-all',
                color: 'var(--color-text-1)',
              }}
            >
              {v}
            </span>
          </div>
        ))}
      </div>
    </Drawer>
  );
};

// ─── Square Grid (prefixlen >= 24) ────────────────────────────────────────────

const COLS = 16;
const CELL_SIZE = 28;
const CELL_GAP = 3;

interface SquareGridProps {
  data: IpamViewData;
  baseOffset?: number; // first host number (default 1 for /24)
}

const SquareGrid: React.FC<SquareGridProps> = ({ data, baseOffset = 1 }) => {
  const { t } = useTranslation();
  const octetMap = buildOctetMap(data.ips);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedIp, setSelectedIp] = useState<IpInstance | null>(null);

  // Pan + zoom state
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragging = useRef(false);
  const dragStart = useRef({ mx: 0, my: 0, px: 0, py: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    setScale((s) => Math.min(3, Math.max(0.3, s - e.deltaY * 0.001)));
  }, []);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    // Only pan on background (not on cells)
    if ((e.target as HTMLElement).dataset.role === 'cell') return;
    dragging.current = true;
    dragStart.current = { mx: e.clientX, my: e.clientY, px: pan.x, py: pan.y };
  }, [pan]);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging.current) return;
    setPan({
      x: dragStart.current.px + e.clientX - dragStart.current.mx,
      y: dragStart.current.py + e.clientY - dragStart.current.my,
    });
  }, []);

  const onMouseUp = useCallback(() => { dragging.current = false; }, []);

  const cells: Array<{ hostNum: number; ip: IpInstance | null; kind: CellKind }> = [];
  for (let i = 0; i < data.capacity; i++) {
    const hostNum = baseOffset + i;
    const ip = octetMap.get(hostNum) ?? null;
    const kind: CellKind = ip ? ipToCellKind(ip) : 'free';
    cells.push({ hostNum, ip, kind });
  }

  const gridWidth = COLS * (CELL_SIZE + CELL_GAP) - CELL_GAP;
  const rows = Math.ceil(data.capacity / COLS);
  const gridHeight = rows * (CELL_SIZE + CELL_GAP) - CELL_GAP;

  const handleCellClick = (ip: IpInstance | null) => {
    if (!ip) return; // free cell — nothing to show
    setSelectedIp(ip);
    setDrawerOpen(true);
  };

  return (
    <>
      <div
        ref={containerRef}
        style={{
          overflow: 'hidden',
          border: '1px solid var(--color-border-2)',
          borderRadius: 8,
          background: 'var(--color-bg-2)',
          cursor: dragging.current ? 'grabbing' : 'grab',
          userSelect: 'none',
          minHeight: 200,
          position: 'relative',
        }}
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        <div
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
            transformOrigin: '0 0',
            padding: 16,
            width: gridWidth + 32,
            height: gridHeight + 32,
          }}
        >
          <svg
            width={gridWidth}
            height={gridHeight}
            style={{ display: 'block', overflow: 'visible' }}
          >
            {cells.map(({ hostNum, ip, kind }) => {
              const idx = hostNum - baseOffset;
              const col = idx % COLS;
              const row = Math.floor(idx / COLS);
              const x = col * (CELL_SIZE + CELL_GAP);
              const y = row * (CELL_SIZE + CELL_GAP);
              const color = KIND_COLOR[kind];
              const isFree = kind === 'free';
              const ipAddr = ip?.ip_addr ?? `${data.subnet_address.split('.').slice(0, 3).join('.')}.${hostNum}`;
              const label = String(hostNum);

              const tooltipTitle = (
                <div style={{ fontSize: 12 }}>
                  <div><strong>{ipAddr}</strong></div>
                  {ip && (
                    <>
                      {ip.ip_status && ip.ip_status.length > 0 && (
                        <div>{t('Model.ipViewTooltipStatus')}: {ip.ip_status.join(', ')}</div>
                      )}
                      {ip.ip_allocated_status && ip.ip_allocated_status.length > 0 && (
                        <div>{t('Model.ipViewTooltipType')}: {ip.ip_allocated_status.join(', ')}</div>
                      )}
                      {ip.inst_name && (
                        <div>{t('Model.ipViewTooltipUser')}: {ip.inst_name}</div>
                      )}
                    </>
                  )}
                </div>
              );

              return (
                <Tooltip key={hostNum} title={tooltipTitle} placement="top">
                  <g
                    style={{ cursor: ip ? 'pointer' : 'default' }}
                    onClick={() => handleCellClick(ip)}
                    data-role="cell"
                  >
                    <rect
                      x={x}
                      y={y}
                      width={CELL_SIZE}
                      height={CELL_SIZE}
                      rx={4}
                      fill={isFree ? 'transparent' : color}
                      stroke={color}
                      strokeWidth={isFree ? 1 : 0}
                      opacity={isFree ? 0.4 : 0.85}
                      data-role="cell"
                    />
                    <text
                      x={x + CELL_SIZE / 2}
                      y={y + CELL_SIZE / 2 + 4}
                      textAnchor="middle"
                      fontSize={9}
                      fill={isFree ? color : '#fff'}
                      pointerEvents="none"
                      data-role="cell"
                    >
                      {label}
                    </text>
                  </g>
                </Tooltip>
              );
            })}
          </svg>
        </div>
        <div
          style={{
            position: 'absolute',
            bottom: 8,
            right: 12,
            fontSize: 11,
            color: 'var(--color-text-3)',
            pointerEvents: 'none',
          }}
        >
          scroll to zoom · drag to pan
        </div>
      </div>
      <IpDetailDrawer
        ip={selectedIp}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </>
  );
};

// ─── Heat view for prefixlen < 24 (one block per /24) ────────────────────────

interface HeatBlock {
  prefix: string; // e.g. "10.0.1"
  base: string;   // e.g. "10.0.1.0/24"
  totalSlots: number;
  usedSlots: number;
  ips: IpInstance[];
}

interface HeatViewProps {
  data: IpamViewData;
  onDrill: (block: HeatBlock) => void;
}

const HeatView: React.FC<HeatViewProps> = ({ data, onDrill }) => {
  const { t } = useTranslation();

  // Group stored IPs by their /24 prefix
  const blockMap = new Map<string, IpInstance[]>();
  for (const ip of data.ips) {
    const parts = ip.ip_addr.split('.');
    if (parts.length !== 4) continue;
    const prefix = parts.slice(0, 3).join('.');
    if (!blockMap.has(prefix)) blockMap.set(prefix, []);
    blockMap.get(prefix)!.push(ip);
  }

  // Determine total /24 blocks from subnet
  const prefixlen = data.prefixlen;
  const subnetParts = data.subnet_address.split('.').map(Number);

  // Number of /24 blocks = 2^(24-prefixlen) if prefixlen <= 24
  const numBlocks = prefixlen <= 24 ? Math.pow(2, 24 - prefixlen) : 1;
  const cappedBlocks = Math.min(numBlocks, 256); // display cap for very large ranges

  // Build block list
  const blocks: HeatBlock[] = [];
  for (let i = 0; i < cappedBlocks; i++) {
    // Compute the /24 subnet address
    let thirdOctet = subnetParts[2] + i;
    const secondOctet = subnetParts[1] + Math.floor(thirdOctet / 256);
    thirdOctet = thirdOctet % 256;
    const prefix = `${subnetParts[0]}.${secondOctet}.${thirdOctet}`;
    const ips = blockMap.get(prefix) ?? [];
    blocks.push({
      prefix,
      base: `${prefix}.0/24`,
      totalSlots: 254,
      usedSlots: ips.length,
      ips,
    });
  }

  return (
    <div>
      <p style={{ color: 'var(--color-text-3)', fontSize: 13, marginBottom: 12 }}>
        {t('Model.ipViewDrillTitle')} — {data.subnet_address}/{data.prefixlen}
        {cappedBlocks < numBlocks && ` (showing first ${cappedBlocks} of ${numBlocks})`}
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {blocks.map((block) => {
          const ratio = block.totalSlots > 0 ? block.usedSlots / block.totalSlots : 0;
          const pct = Math.round(ratio * 100);
          const hue = Math.round(120 - ratio * 120); // green → red
          const bg = `hsl(${hue}, 70%, 45%)`;
          return (
            <Tooltip
              key={block.prefix}
              title={`${block.base}  ${pct}% used (${block.usedSlots}/${block.totalSlots})`}
            >
              <div
                onClick={() => onDrill(block)}
                style={{
                  width: 80,
                  height: 56,
                  borderRadius: 6,
                  background: bg,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  color: '#fff',
                  fontSize: 11,
                  fontFamily: 'monospace',
                  opacity: 0.88,
                  transition: 'opacity 0.15s',
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.opacity = '0.88'; }}
              >
                <span style={{ fontWeight: 600 }}>{block.prefix}.x</span>
                <span>{pct}%</span>
              </div>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
};

// ─── Main IpamMatrix component ─────────────────────────────────────────────────

interface IpamMatrixProps {
  instId: string;
}

interface DrillState {
  block: {
    prefix: string;
    base: string;
    totalSlots: number;
    usedSlots: number;
    ips: IpInstance[];
  };
}

const IpamMatrix: React.FC<IpamMatrixProps> = ({ instId }) => {
  const { t } = useTranslation();
  const { getIpamView } = useInstanceApi();

  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<IpamViewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drill, setDrill] = useState<DrillState | null>(null);

  useEffect(() => {
    if (!instId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDrill(null);
    getIpamView(instId)
      .then((res: IpamViewData) => {
        if (!cancelled) setData(res ?? null);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err?.message ?? 'Failed to load IPAM data');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [instId]);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: 'var(--color-danger)' }}>
        {error}
      </div>
    );
  }

  if (!data || !data.subnet_address || !data.subnet_mask) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <Empty description={t('Model.ipViewEmptyHint')} />
      </div>
    );
  }

  const isSmallSubnet = data.prefixlen >= 24;

  // Drilled-in /24 view for a large subnet block
  if (drill) {
    const drillData: IpamViewData = {
      ...data,
      subnet_address: `${drill.block.prefix}.0`,
      prefixlen: 24,
      capacity: 254,
      used: drill.block.usedSlots,
      available: 254 - drill.block.usedSlots,
      ratio: drill.block.usedSlots / 254,
      ips: drill.block.ips,
    };
    return (
      <div style={{ padding: '0 4px' }}>
        <Button
          icon={<ArrowLeftOutlined />}
          size="small"
          type="link"
          style={{ paddingLeft: 0, marginBottom: 8 }}
          onClick={() => setDrill(null)}
        >
          {t('Model.ipViewBack')} — {data.subnet_address}/{data.prefixlen}
        </Button>
        <SummaryBar data={drillData} />
        <Legend />
        <div style={{ marginTop: 8 }}>
          <SquareGrid data={drillData} baseOffset={1} />
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: '0 4px' }}>
      <SummaryBar data={data} />
      <Legend />
      <div style={{ marginTop: 8 }}>
        {isSmallSubnet ? (
          <SquareGrid data={data} baseOffset={1} />
        ) : (
          <HeatView
            data={data}
            onDrill={(block) => setDrill({ block })}
          />
        )}
      </div>
    </div>
  );
};

export default IpamMatrix;
