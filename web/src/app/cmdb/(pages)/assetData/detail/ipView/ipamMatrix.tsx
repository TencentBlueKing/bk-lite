'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { Spin, Tooltip, Button, message } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi } from '@/app/cmdb/api/instance';
import usePermissions from '@/hooks/usePermissions';
import IpDetailDrawer from './IpDetailDrawer';
import {
  KIND_COLOR,
  buildOctetMap,
  ipToCellKind,
  type CellKind,
  type IpInstance,
} from './ipamCells';
import { IPAM_ASSET_PERMISSION_PATH, type IpamEditPayload } from './ipamEdit';

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

interface SummaryBarProps {
  data: IpamViewData;
}

const SummaryBar: React.FC<SummaryBarProps> = ({ data }) => {
  const { t } = useTranslation();
  const pct = Math.round(data.ratio * 100);
  return (
    <div className="flex flex-wrap items-center gap-6 py-2 pb-3">
      <span className="text-[13px] text-[var(--color-text-3)]">
        {data.subnet_address}/{data.prefixlen}
      </span>
      <span>
        <span className="mr-1 text-xs text-[var(--color-text-3)]">{t('Model.ipViewCapacity')}:</span>
        <strong>{data.capacity}</strong>
      </span>
      <span>
        <span className="mr-1 text-xs text-[var(--color-text-3)]">{t('Model.ipViewUsed')}:</span>
        <strong className="text-[var(--color-primary)]">{data.used}</strong>
      </span>
      <span>
        <span className="mr-1 text-xs text-[var(--color-text-3)]">{t('Model.ipViewAvailable')}:</span>
        <strong className="text-[var(--color-success)]">{data.available}</strong>
      </span>
      <span>
        <span className="mr-1 text-xs text-[var(--color-text-3)]">{t('Model.ipViewRatio')}:</span>
        <strong className={pct > 80 ? 'text-[var(--color-danger)]' : 'text-[var(--color-primary)]'}>{pct}%</strong>
      </span>
      <div className="mt-0.5 h-1.5 basis-full overflow-hidden rounded-sm bg-[var(--color-fill-2)]">
        <div
          className="h-full transition-[width] duration-300"
          style={{
            width: `${pct}%`,
            background: pct > 80 ? 'var(--color-danger)' : 'var(--color-primary)',
          }}
        />
      </div>
    </div>
  );
};

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
    <div className="flex flex-wrap gap-x-5 gap-y-2 py-2">
      {items.map(({ kind, label }) => (
        <span key={kind} className="flex items-center gap-1.5 text-xs">
          <span
            className="inline-block h-3.5 w-3.5 shrink-0 rounded-sm"
            style={{ background: KIND_COLOR[kind] }}
          />
          <span className="text-[var(--color-text-2)]">{label}</span>
        </span>
      ))}
    </div>
  );
};

const CELL_MIN = 40;
const CELL_H = 36;

interface SquareGridProps {
  data: IpamViewData;
  subnetInstUuid: string;
  baseOffset?: number;
  onReload: () => Promise<void>;
}

const SquareGrid: React.FC<SquareGridProps> = ({
  data,
  subnetInstUuid,
  baseOffset = 1,
  onReload,
}) => {
  const { t } = useTranslation();
  const { saveIpamIp } = useInstanceApi();
  const { hasPermission } = usePermissions(IPAM_ASSET_PERMISSION_PATH);
  const hasAdd = hasPermission(['Add']);
  const hasEdit = hasPermission(['Edit']);
  const hasDelete = hasPermission(['Delete']);
  const octetMap = buildOctetMap(data.ips);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedIp, setSelectedIp] = useState<IpInstance | null>(null);
  const [saving, setSaving] = useState(false);

  const cells: Array<{ hostNum: number; ip: IpInstance | null; kind: CellKind }> = [];
  for (let i = 0; i < data.capacity; i++) {
    const hostNum = baseOffset + i;
    const ip = octetMap.get(hostNum) ?? null;
    const kind: CellKind = ip ? ipToCellKind(ip) : 'free';
    cells.push({ hostNum, ip, kind });
  }

  const subnetPrefix = data.subnet_address.split('.').slice(0, 3).join('.');

  const handleCellClick = (hostNum: number, ip: IpInstance | null) => {
    if (ip) {
      setSelectedIp(ip);
      setDrawerOpen(true);
      return;
    }
    if (!hasAdd) return;
    setSelectedIp({
      ip_addr: `${subnetPrefix}.${hostNum}`,
      ip_allocated_status: ['allocated'],
    });
    setDrawerOpen(true);
  };

  const handleSave = async (payload: IpamEditPayload) => {
    setSaving(true);
    try {
      await saveIpamIp(payload);
      message.success(t('common.saveSuccess'));
      setDrawerOpen(false);
      setSelectedIp(null);
      await onReload();
    } catch (error) {
      console.error(error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <style>{`
        .ipam-cell { transition: transform .12s ease, box-shadow .12s ease; }
        .ipam-cell:hover { transform: translateY(-2px); box-shadow: 0 4px 10px rgba(0,0,0,.18); z-index: 1; }
      `}</style>
      <div
        className="grid gap-1 rounded-[10px] border border-[var(--color-border-2)] bg-[var(--color-bg-2)] p-4"
        style={{
          gridTemplateColumns: `repeat(auto-fill, minmax(${CELL_MIN}px, 1fr))`,
        }}
      >
        {cells.map(({ hostNum, ip, kind }) => {
          const color = KIND_COLOR[kind];
          const isFree = kind === 'free';
          const ipAddr = ip?.ip_addr ?? `${subnetPrefix}.${hostNum}`;
          const clickable = Boolean(ip) || hasAdd;

          const tooltipTitle = (
            <div className="text-xs">
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
            <Tooltip key={hostNum} title={tooltipTitle} placement="top" mouseEnterDelay={0.15}>
              <div
                className={`ipam-cell flex select-none items-center justify-center rounded-md text-[11px] tabular-nums ${clickable ? 'cursor-pointer' : 'cursor-default'} ${isFree ? 'font-normal' : 'font-semibold text-white'}`}
                onClick={() => handleCellClick(hostNum, ip)}
                style={{
                  height: CELL_H,
                  background: isFree ? 'rgba(82,196,26,0.12)' : color,
                  border: `1px solid ${isFree ? 'rgba(82,196,26,0.35)' : color}`,
                  color: isFree ? '#389e0d' : undefined,
                }}
              >
                {hostNum}
              </div>
            </Tooltip>
          );
        })}
      </div>
      <IpDetailDrawer
        ip={selectedIp}
        open={drawerOpen}
        subnetInstUuid={subnetInstUuid}
        hasAdd={hasAdd}
        hasEdit={hasEdit}
        hasDelete={hasDelete}
        saving={saving}
        onClose={() => setDrawerOpen(false)}
        onSave={handleSave}
      />
    </>
  );
};

interface HeatBlock {
  prefix: string;
  base: string;
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

  const blockMap = new Map<string, IpInstance[]>();
  for (const ip of data.ips) {
    const parts = ip.ip_addr.split('.');
    if (parts.length !== 4) continue;
    const prefix = parts.slice(0, 3).join('.');
    if (!blockMap.has(prefix)) blockMap.set(prefix, []);
    blockMap.get(prefix)!.push(ip);
  }

  const prefixlen = data.prefixlen;
  const subnetParts = data.subnet_address.split('.').map(Number);
  const numBlocks = prefixlen <= 24 ? Math.pow(2, 24 - prefixlen) : 1;
  const cappedBlocks = Math.min(numBlocks, 256);

  const blocks: HeatBlock[] = [];
  for (let i = 0; i < cappedBlocks; i++) {
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
      <p className="mb-3 text-[13px] text-[var(--color-text-3)]">
        {t('Model.ipViewDrillTitle')} — {data.subnet_address}/{data.prefixlen}
        {cappedBlocks < numBlocks && ` (showing first ${cappedBlocks} of ${numBlocks})`}
      </p>
      <div className="flex flex-wrap gap-2">
        {blocks.map((block) => {
          const ratio = block.totalSlots > 0 ? block.usedSlots / block.totalSlots : 0;
          const pct = Math.round(ratio * 100);
          const hue = Math.round(120 - ratio * 120);
          const bg = `hsl(${hue}, 70%, 45%)`;
          return (
            <Tooltip
              key={block.prefix}
              title={`${block.base}  ${pct}% used (${block.usedSlots}/${block.totalSlots})`}
            >
              <div
                onClick={() => onDrill(block)}
                className="flex h-14 w-20 cursor-pointer flex-col items-center justify-center rounded-md font-mono text-[11px] text-white opacity-90 transition-opacity hover:opacity-100"
                style={{ background: bg }}
              >
                <span className="font-semibold">{block.prefix}.x</span>
                <span>{pct}%</span>
              </div>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
};

interface IpamMatrixProps {
  instUuid: string;
}

interface DrillState {
  block: HeatBlock;
}

const IpamMatrix: React.FC<IpamMatrixProps> = ({ instUuid }) => {
  const { t } = useTranslation();
  const { getIpamView } = useInstanceApi();

  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<IpamViewData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drill, setDrill] = useState<DrillState | null>(null);

  const load = useCallback(async () => {
    if (!instUuid) return;
    setLoading(true);
    setError(null);
    setDrill(null);
    try {
      const res = await getIpamView(instUuid);
      setData((res as IpamViewData) ?? null);
    } catch (err) {
      const messageText = err instanceof Error ? err.message : 'Failed to load IPAM data';
      setError(messageText);
    } finally {
      setLoading(false);
    }
  }, [instUuid, getIpamView]);

  const reload = useCallback(async () => {
    if (!instUuid) return;
    try {
      const res = await getIpamView(instUuid);
      setData((res as IpamViewData) ?? null);
    } catch (err) {
      console.error(err);
    }
  }, [instUuid, getIpamView]);

  useEffect(() => {
    void load();
    // 仅在子网切换时重拉；getIpamView 每次 render 都是新函数。
  }, [instUuid]);

  if (loading && !data) {
    return (
      <div className="flex justify-center p-[60px]">
        <Spin size="large" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="p-10 text-center text-[var(--color-danger)]">
        {error}
      </div>
    );
  }

  if (!data || !data.subnet_address || !data.subnet_mask) {
    return (
      <div className="p-10 text-center">
        <CompactEmptyState description={t('Model.ipViewEmptyHint')} />
      </div>
    );
  }

  const isSmallSubnet = data.prefixlen >= 24;

  if (drill) {
    const drillIps = data.ips.filter((ip) => {
      const parts = ip.ip_addr.split('.');
      return parts.length === 4 && parts.slice(0, 3).join('.') === drill.block.prefix;
    });
    const drillData: IpamViewData = {
      ...data,
      subnet_address: `${drill.block.prefix}.0`,
      prefixlen: 24,
      capacity: 254,
      used: drillIps.length,
      available: 254 - drillIps.length,
      ratio: drillIps.length / 254,
      ips: drillIps,
    };
    return (
      <div className="px-1">
        <Button
          icon={<ArrowLeftOutlined />}
          size="small"
          type="link"
          className="mb-2 pl-0"
          onClick={() => setDrill(null)}
        >
          {t('Model.ipViewBack')} — {data.subnet_address}/{data.prefixlen}
        </Button>
        <SummaryBar data={drillData} />
        <Legend />
        <div className="mt-2">
          <SquareGrid
            data={drillData}
            subnetInstUuid={instUuid}
            baseOffset={1}
            onReload={reload}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="px-1">
      <SummaryBar data={data} />
      <Legend />
      <div className="mt-2">
        {isSmallSubnet ? (
          <SquareGrid
            data={data}
            subnetInstUuid={instUuid}
            baseOffset={1}
            onReload={reload}
          />
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
