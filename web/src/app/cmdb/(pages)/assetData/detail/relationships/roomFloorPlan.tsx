'use client';

import React, { useEffect, useState } from 'react';
import { Spin, Empty, Alert, Drawer, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
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
            <i style={{ background: rackTypeColor(k), boxShadow: `0 0 6px ${rackTypeColor(k)}` }} />
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
                  borderColor: `${c}66`,
                  boxShadow: `0 0 0 1px ${c}22, 0 6px 20px -8px ${c}aa, inset 0 1px 0 rgba(255,255,255,0.05)`,
                }}
                onClick={() => setRack(r)}>
                <span className="rf-rack-top" style={{ background: c, boxShadow: `0 0 10px ${c}` }} />
                <span className="rf-rack-led" style={{ background: c, boxShadow: `0 0 8px ${c}` }} />
                <div className="rf-rack-name" title={r.inst_name}>{r.inst_name}</div>
                <div className="rf-rack-type" style={{ color: c }}>
                  {rackTypeName(r.datacenter_type)} · {r.u_count}U
                </div>
                <div className="rf-rack-free"
                  title={`${t('Model.rackContiguousFree')} ${r.max_free_u}U`}>
                  {t('Model.rackContiguousFreeShort')} <b>{r.max_free_u}</b>U
                </div>
                <div className="rf-bar">
                  <i style={{ width: `${Math.min(r.usage, 100)}%`, background: c, boxShadow: `0 0 8px ${c}` }} />
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
        width={500}
        title={null}
        closable={false}
        styles={{
          body: { padding: 0, background: TECH.bg1 },
          content: { background: TECH.bg1 },
          wrapper: { boxShadow: '-12px 0 40px rgba(0,0,0,0.5)' },
        }}
      >
        {rack && (
          <div className="rd">
            <div className="rd-hd" style={{
              background: `linear-gradient(180deg, ${rackTypeColor(rack.datacenter_type)}22, ${TECH.bg1})`,
              borderBottom: `1px solid ${TECH.line}`,
            }}>
              <span className="rd-led" style={{
                background: rackTypeColor(rack.datacenter_type),
                boxShadow: `0 0 12px ${rackTypeColor(rack.datacenter_type)}`,
              }} />
              <div style={{ minWidth: 0, flex: 1 }}>
                <div className="rd-name" title={rack.inst_name}>{rack.inst_name}</div>
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
        .rf { padding: 12px; }
        .rf-legend {
          display: flex; align-items: center; flex-wrap: wrap; gap: 16px;
          padding: 8px 14px; margin-bottom: 10px;
          border-radius: 10px; border: 1px solid ${TECH.line};
          background: linear-gradient(180deg, ${TECH.panel}, ${TECH.bg1});
        }
        .rf-legend-t { color: ${TECH.textDim}; font-size: 12px; }
        .rf-legend-i {
          display: inline-flex; align-items: center; gap: 6px;
          color: ${TECH.text}; font-size: 12px;
        }
        .rf-legend-i > i {
          width: 11px; height: 11px; border-radius: 3px; display: inline-block;
        }
        .rf-stage {
          border-radius: 14px; padding: 18px; overflow: auto;
          background:
            radial-gradient(1200px 500px at 20% -10%, ${TECH.panelHi}, transparent),
            linear-gradient(180deg, ${TECH.bg1}, ${TECH.bg0});
          border: 1px solid ${TECH.line};
          box-shadow: inset 0 0 60px rgba(0,0,0,0.4);
        }
        .rf-canvas {
          position: relative;
          background-image:
            linear-gradient(${TECH.line} 1px, transparent 1px),
            linear-gradient(90deg, ${TECH.line} 1px, transparent 1px);
          background-size: ${CELL}px ${CELL}px, ${CELL}px ${CELL}px;
          background-position: ${PAD}px ${PAD}px, ${PAD}px ${PAD}px;
        }
        .rf-hdr {
          position: absolute; color: ${TECH.cyan}; opacity: .85;
          font-family: ui-monospace, monospace; font-size: 12px;
          display: flex; align-items: center; justify-content: center;
        }
        .rf-col { top: 8px; height: 28px; }
        .rf-row { left: 4px; width: 28px; }
        .rf-cell {
          position: absolute; border-radius: 8px;
          border: 1px dashed ${TECH.line};
        }
        .rf-rack {
          position: absolute; border-radius: 10px; cursor: pointer;
          border: 1px solid; overflow: hidden;
          background: linear-gradient(160deg, ${TECH.panelHi}, ${TECH.panel});
          transition: transform .14s ease, box-shadow .14s ease;
          padding: 11px 9px 8px;
        }
        .rf-rack:hover { transform: translateY(-3px); }
        .rf-rack-top {
          position: absolute; top: 0; left: 0; right: 0; height: 3px;
        }
        .rf-rack-led {
          position: absolute; top: 9px; right: 9px;
          width: 7px; height: 7px; border-radius: 50%;
        }
        .rf-rack-name {
          color: #fff; font-size: 12px; font-weight: 600; line-height: 1.2;
          letter-spacing: -0.2px;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
          margin-top: 2px; padding-right: 12px;
        }
        .rf-rack-type {
          font-size: 10.5px; margin-top: 3px; font-weight: 500;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .rf-rack-free {
          font-size: 10.5px; margin-top: 4px; color: ${TECH.cyan};
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .rf-rack-free > b { font-weight: 600; font-family: ui-monospace, monospace; }
        .rf-bar {
          position: absolute; left: 10px; right: 10px; bottom: 18px; height: 5px;
          border-radius: 3px; background: rgba(255,255,255,0.08); overflow: hidden;
        }
        .rf-bar > i { display: block; height: 100%; border-radius: 3px; }
        .rf-rack-usage {
          position: absolute; right: 10px; bottom: 5px;
          font-size: 10px; color: ${TECH.textDim}; font-family: ui-monospace, monospace;
        }
        .rd { color: ${TECH.text}; display: flex; flex-direction: column;
          min-height: 100%; background: ${TECH.bg1}; }
        .rd-hd { display: flex; align-items: center; gap: 12px; padding: 18px 20px; }
        .rd-led { width: 11px; height: 11px; border-radius: 50%; flex: none; }
        .rd-name {
          font-size: 17px; font-weight: 600; color: #fff;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .rd-sub { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
        .rd-meta { font-size: 12px; color: ${TECH.textDim}; font-family: ui-monospace, monospace; }
      `}</style>
    </div>
  );
};

export default RoomFloorPlan;
