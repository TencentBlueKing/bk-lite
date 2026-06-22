'use client';

import React, { useEffect, useState } from 'react';
import { Spin, Empty, Alert, Drawer, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useInstanceApi } from '@/app/cmdb/api/instance';
import type { RoomLayoutData, RoomRack, RackDevice } from '@/app/cmdb/types/rackRoom';
import {
  CELL, PAD, GAP, cellXY, roomGridSize, rackTypeColor, rackTypeName, TECH,
} from '@/app/cmdb/utils/rackRoomLayout';
import RackElevation from './rackElevation';
import DeviceDetailDrawer from './deviceDetailDrawer';

interface Props {
  modelId: string;
  instId: string;
}

const RoomFloorPlan: React.FC<Props> = ({ modelId, instId }) => {
  const { t } = useTranslation();
  const { getRoomLayout } = useInstanceApi();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<RoomLayoutData | null>(null);
  const [rack, setRack] = useState<RoomRack | null>(null);
  const [device, setDevice] = useState<RackDevice | null>(null);
  const [devOpen, setDevOpen] = useState(false);

  useEffect(() => {
    if (!modelId || !instId) return;
    let cancelled = false;
    setLoading(true);
    getRoomLayout(modelId, instId)
      .then((res: RoomLayoutData) => !cancelled && setData(res))
      .catch(() => !cancelled && setData(null))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, instId]);

  if (loading) return <div style={{ padding: 60, textAlign: 'center' }}><Spin spinning /></div>;
  if (!data) return <Empty description={t('Model.noRoomLayout')} />;
  if (!data.racks.length && !data.unplaced.length)
    return <Empty description={t('Model.emptyRoom')} />;

  const { cols, rows } = roomGridSize(data);
  const width = PAD + cols * CELL + 16;
  const height = PAD + rows * CELL + 16;
  const box = CELL - GAP;

  return (
    <div className="rf">
      <div className="rf-legend">
        <span className="rf-legend-t">{t('Model.legend')}</span>
        {['1', '2', '3', '4', '5', 'other'].map((k) => (
          <span key={k} className="rf-legend-i">
            <i style={{ background: rackTypeColor(k) }} />
            {rackTypeName(k)}
          </span>
        ))}
      </div>
      <div className="rf-stage">
        <div className="rf-canvas" style={{ width, height }}>
          {/* 列标题 A.. */}
          {Array.from({ length: cols }, (_, i) => (
            <span key={`c${i}`} className="rf-hdr rf-col"
              style={{ left: PAD + i * CELL, width: CELL }}>
              {String.fromCharCode(65 + i)}
            </span>
          ))}
          {/* 行标题 1.. */}
          {Array.from({ length: rows }, (_, i) => (
            <span key={`r${i}`} className="rf-hdr rf-row"
              style={{ top: PAD + i * CELL, height: CELL }}>{i + 1}</span>
          ))}
          {/* 空网格位 */}
          {Array.from({ length: rows }).flatMap((_, ri) =>
            Array.from({ length: cols }).map((__, ci) => {
              const { x, y } = cellXY(ri + 1, ci + 1);
              return (
                <div key={`g${ri}-${ci}`} className="rf-cell"
                  style={{ left: x + GAP / 2, top: y + GAP / 2, width: box, height: box }} />
              );
            })
          )}
          {/* 机柜 */}
          {data.racks.map((r) => {
            const { x, y } = cellXY(r.row, r.col);
            const c = rackTypeColor(r.datacenter_type);
            return (
              <div key={r.inst_id} className="rf-rack"
                style={{
                  left: x + GAP / 2, top: y + GAP / 2, width: box, height: box,
                  borderColor: `color-mix(in srgb, ${c} 22%, rgba(41, 61, 93, 0.16))`,
                  boxShadow: '0 1px 2px rgba(24, 39, 63, 0.07), 0 10px 22px rgba(31, 51, 82, 0.045)',
                  ['--rack-tone' as string]: c,
                }}
                onClick={() => setRack(r)}>
                <span className="rf-rack-led" style={{ background: c, boxShadow: `0 0 0 3px ${c}1f` }} />
                <EllipsisWithTooltip text={r.inst_name} className="rf-rack-name" />
                <div className="rf-rack-type" style={{ color: c }}>
                  {rackTypeName(r.datacenter_type)} · {r.u_count}U
                </div>
                <div className="rf-rack-free"
                  title={`${t('Model.rackContiguousFree')} ${r.max_free_u}U`}>
                  {t('Model.rackContiguousFreeShort')} <b>{r.max_free_u}</b>U
                </div>
                <div className="rf-bar">
                  <i style={{ width: `${Math.min(r.usage, 100)}%`, background: c }} />
                </div>
                <div className="rf-rack-usage">{r.usage}%</div>
              </div>
            );
          })}
        </div>
      </div>

      {data.conflicts.length > 0 && (
        <Alert style={{ marginTop: 12 }} type="error" showIcon
          message={t('Model.rackCellConflict')} />
      )}
      {data.unplaced.length > 0 && (
        <Alert style={{ marginTop: 12 }} type="warning" showIcon
          message={`${t('Model.rackNoPosition')}: ${data.unplaced.map((u) => u.inst_name).join('、')}`} />
      )}

      {/* 机柜抽屉：正视 U 图 */}
      <Drawer
        open={!!rack}
        onClose={() => setRack(null)}
        width={640}
        title={null}
        closable={false}
        styles={{
          body: { padding: 0, background: TECH.bg1 },
          content: { background: TECH.bg1 },
          wrapper: { boxShadow: '-12px 0 40px rgba(23,54,106,0.15)' },
        }}
      >
        {rack && (
          <div className="rd">
            <div className="rd-hd" style={{
              background: 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
              borderBottom: `1px solid ${TECH.line}`,
            }}>
              <span className="rd-led" style={{
                background: rackTypeColor(rack.datacenter_type),
                boxShadow: `0 0 0 4px ${rackTypeColor(rack.datacenter_type)}18`,
              }} />
              <div style={{ minWidth: 0, flex: 1 }}>
                <EllipsisWithTooltip text={rack.inst_name} className="rd-name" />
                <div className="rd-sub">
                  <Tag style={{
                    background: 'transparent', margin: 0,
                    borderColor: rackTypeColor(rack.datacenter_type),
                    color: rackTypeColor(rack.datacenter_type),
                  }}>{rackTypeName(rack.datacenter_type)}</Tag>
                  <span className="rd-meta">{rack.col_letter}{rack.row} · {rack.u_count}U · {t('Model.rackUsage')} {rack.usage}%</span>
                </div>
              </div>
            </div>
            <RackElevation
              modelId="rack"
              instId={rack.inst_id}
              embedded
              onDeviceClick={(d) => { setDevice(d); setDevOpen(true); }}
            />
          </div>
        )}
      </Drawer>

      <DeviceDetailDrawer device={device} open={devOpen} onClose={() => setDevOpen(false)} />

      <style jsx>{`
        .rf {
          padding: 12px;
          color: ${TECH.text};
          background: linear-gradient(180deg, #f8fbff 0%, ${TECH.bg1} 52%, #eef4fb 100%);
          border-radius: 10px;
        }
        .rf-legend {
          display: flex; align-items: center; flex-wrap: wrap; gap: 16px;
          min-height: 36px;
          padding: 5px 6px;
          margin-bottom: 12px;
          border-radius: 8px;
          border: 1px solid ${TECH.line};
          background: #f8fafc;
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.9);
        }
        .rf-legend-t {
          display: inline-flex;
          align-items: center;
          min-height: 24px;
          padding: 0 8px;
          color: ${TECH.textDim};
          font-size: 11px;
          font-weight: 650;
        }
        .rf-legend-i {
          display: inline-flex; align-items: center; gap: 6px;
          min-height: 24px;
          padding: 0 8px;
          border: 1px solid rgba(43, 63, 96, 0.10);
          border-radius: 999px;
          background: #ffffff;
          color: #536176; font-size: 11px; font-weight: 650;
        }
        .rf-legend-i > i {
          width: 8px; height: 8px; border-radius: 2px; display: inline-block;
        }
        .rf-stage {
          border-radius: 10px; padding: 10px; overflow: auto;
          background: rgba(255,255,255,0.9);
          border: 1px solid ${TECH.line};
          box-shadow: 0 18px 42px rgba(31, 47, 75, 0.07);
        }
        .rf-canvas {
          position: relative;
          overflow: hidden;
          border: 1px solid rgba(43, 63, 96, 0.08);
          border-radius: 9px;
          background-color: #f6f9fd;
          background-image:
            linear-gradient(rgba(58, 83, 125, 0.11) 1px, transparent 1px),
            linear-gradient(90deg, rgba(58, 83, 125, 0.11) 1px, transparent 1px);
          background-size: ${CELL}px ${CELL}px, ${CELL}px ${CELL}px;
          background-position: ${PAD}px ${PAD}px, ${PAD}px ${PAD}px;
        }
        .rf-canvas::before {
          content: "";
          position: absolute;
          left: ${PAD}px;
          right: 0;
          top: calc(${PAD}px + ${CELL}px * 2);
          height: ${CELL}px;
          z-index: 0;
          pointer-events: none;
          opacity: .42;
          background:
            linear-gradient(90deg, transparent, rgba(255, 255, 255, .58), transparent),
            repeating-linear-gradient(135deg, rgba(43, 63, 96, .06) 0 1px, transparent 1px 10px);
        }
        .rf-hdr {
          position: absolute; z-index: 3; color: ${TECH.cyan}; opacity: .95;
          font-family: ui-monospace, monospace; font-size: 11px;
          font-weight: 700;
          display: flex; align-items: center; justify-content: center;
        }
        .rf-col { top: 8px; height: 28px; }
        .rf-row { left: 4px; width: 28px; }
        .rf-cell {
          position: absolute; z-index: 1; border-radius: 9px;
          border: 1px solid rgba(75, 96, 130, 0.08);
          background: linear-gradient(180deg, rgba(255,255,255,0.34), rgba(255,255,255,0.16));
        }
        .rf-rack {
          position: absolute; z-index: 2; border-radius: 10px; cursor: pointer;
          border: 1px solid; overflow: hidden;
          background:
            radial-gradient(circle at 100% 0%, color-mix(in srgb, var(--rack-tone) 9%, transparent), transparent 40%),
            linear-gradient(180deg, color-mix(in srgb, var(--rack-tone) 3%, #ffffff), #f9fbfe);
          transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
          padding: 11px 10px 9px;
        }
        .rf-rack::before {
          content: "";
          position: absolute;
          inset: 6px;
          border-radius: 7px;
          border: 1px solid color-mix(in srgb, var(--rack-tone) 12%, transparent);
          pointer-events: none;
        }
        .rf-rack:hover {
          transform: translateY(-2px);
          border-color: var(--rack-tone);
          box-shadow:
            0 1px 2px rgba(24, 39, 63, 0.08),
            0 14px 26px rgba(31, 51, 82, 0.10) !important;
        }
        .rf-rack-led {
          position: absolute; top: 10px; right: 10px;
          width: 7px; height: 7px; border-radius: 50%;
        }
        :global(.rf-rack-name) {
          color: ${TECH.text}; font-size: 11.5px; font-weight: 760; line-height: 1.2;
          letter-spacing: 0;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
          margin-top: 0; padding-right: 16px;
        }
        .rf-rack-type {
          font-size: 10px; margin-top: 6px; font-weight: 700;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .rf-rack-free {
          font-size: 10px; margin-top: 5px; color: ${TECH.textDim};
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .rf-rack-free > b { font-weight: 600; font-family: ui-monospace, monospace; }
        .rf-bar {
          position: absolute; left: 10px; right: 10px; bottom: 18px; height: 4px;
          border-radius: 999px; background: rgba(23, 32, 51, 0.08); overflow: hidden;
        }
        .rf-bar > i { display: block; height: 100%; border-radius: 999px; }
        .rf-rack-usage {
          position: absolute; right: 10px; bottom: 5px;
          font-size: 10px; color: ${TECH.textDim}; font-family: ui-monospace, monospace;
        }
        .rd { color: ${TECH.text}; display: flex; flex-direction: column;
          min-height: 100%; background: ${TECH.bg1}; }
        .rd-hd { display: flex; align-items: center; gap: 12px; padding: 18px 20px; }
        .rd-led { width: 11px; height: 11px; border-radius: 50%; flex: none; }
        :global(.rd-name) {
          font-size: 17px; font-weight: 600; color: ${TECH.text};
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .rd-sub { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
        .rd-meta { font-size: 12px; color: ${TECH.textDim}; font-family: ui-monospace, monospace; }
      `}</style>
    </div>
  );
};

export default RoomFloorPlan;
