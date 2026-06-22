'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Spin, Empty, Alert } from 'antd';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi } from '@/app/cmdb/api/instance';
import type { RackLayoutData, RackDevice } from '@/app/cmdb/types/rackRoom';
import { RACK_TOP, deviceColor, deviceTypeName, TECH } from '@/app/cmdb/utils/rackRoomLayout';

interface Props {
  modelId: string;
  instId: string;
  embedded?: boolean;
  onDeviceClick?: (d: RackDevice) => void;
}

const FRAME_X = 58;
const FRAME_W = 366;
const INNER_X = FRAME_X + 28;
const INNER_W = FRAME_W - 56;
const DEV_X = INNER_X + 12;
const DEV_W = INNER_W - 24;
const SVG_W = FRAME_X + FRAME_W + 44;
const MIN_U = 9;   // 每 U 最小像素（再小就出滚动条）
const MAX_U = 26;  // 每 U 最大像素（避免太空旷）

const RackElevation: React.FC<Props> = ({ modelId, instId, embedded, onDeviceClick }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const { getRackLayout } = useInstanceApi();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<RackLayoutData | null>(null);
  const [uPx, setUPx] = useState(16);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!modelId || !instId) return;
    let cancelled = false;
    setLoading(true);
    getRackLayout(modelId, instId)
      .then((res: RackLayoutData) => !cancelled && setData(res))
      .catch(() => !cancelled && setData(null))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, instId]);

  // 顶天立地：按从组件顶到视口底的可用高度，动态计算每 U 像素，让机柜撑满
  useEffect(() => {
    const calc = () => {
      const el = scrollRef.current;
      if (!el || !data || !data.u_count) return;
      const top = el.getBoundingClientRect().top;
      const reserve = (data.overlaps.length ? 48 : 0) + (data.unplaced.length ? 48 : 0);
      const avail = window.innerHeight - top - 46 - reserve;
      const per = (avail - RACK_TOP * 2 - 8) / data.u_count;
      setUPx(Math.max(MIN_U, Math.min(MAX_U, per)));
    };
    calc();
    window.addEventListener('resize', calc);
    return () => window.removeEventListener('resize', calc);
  }, [data]);

  const onDevice = (d: RackDevice) => {
    if (onDeviceClick) { onDeviceClick(d); return; }
    const params = new URLSearchParams({
      icn: '', model_name: d.model_id, model_id: d.model_id,
      classification_id: '', inst_id: d.inst_id, inst_name: d.inst_name,
    }).toString();
    router.push(`/cmdb/assetData/detail/baseInfo?${params}`);
  };

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center', background: TECH.bg1 }}>
        <Spin spinning />
      </div>
    );
  }
  if (!data || !data.u_count) return <Empty description={t('Model.noRackLayout')} />;

  const u = data.u_count;
  const svgH = u * uPx + RACK_TOP * 2 + 8;
  const overlapIds = new Set(data.overlaps.flat());
  const yFor = (uStart: number, uSize: number) =>
    RACK_TOP + (u - (uStart + uSize - 1)) * uPx;
  const step = uPx < 13 ? 3 : 2;
  const ruler = Array.from({ length: Math.floor(u / step) + 1 }, (_, i) => i * step || 1)
    .filter((n) => n <= u);

  // 冲突设备分道：U 位重叠的设备改为并排半幅显示，互不完全遮挡
  const lane: Record<string, number> = {};
  const active: { end: number; lane: number }[] = [];
  [...data.placed].sort((a, b) => a.rack_u_start - b.rack_u_start).forEach((d) => {
    for (let i = active.length - 1; i >= 0; i--) {
      if (active[i].end < d.rack_u_start) active.splice(i, 1);
    }
    const used = new Set(active.map((x) => x.lane));
    let l = 0;
    while (used.has(l)) l += 1;
    lane[d.inst_id] = l;
    active.push({ end: d.u_end, lane: l });
  });

  const usedU = u - data.free_u;

  return (
    <div className="rk-wrap" style={{ background: TECH.bg1 }}>
      {/* 概览：总U / 已用 / 空闲 / 连续空闲U位 */}
      <div className="rk-ov">
        <span className="rk-ov-i"><b>{u}</b><i>{t('Model.rackTotalU')}</i></span>
        <span className="rk-ov-i"><b>{usedU}</b><i>{t('Model.rackUsedU')}</i></span>
        <span className="rk-ov-i"><b>{data.free_u}</b><i>{t('Model.rackFreeU')}</i></span>
        <span className="rk-ov-i hl"><b>{data.max_free_u}</b><i>{t('Model.rackContiguousFree')}</i></span>
      </div>
      <div className="rk-scroll" ref={scrollRef}>
        <svg width={SVG_W} height={svgH} style={{ display: 'block', margin: '0 auto' }}>
          <defs>
            <linearGradient id="rkFrame" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="#eef4fb" />
              <stop offset="0.16" stopColor="#f6f9fd" />
              <stop offset="0.5" stopColor="#ffffff" />
              <stop offset="0.84" stopColor="#f6f9fd" />
              <stop offset="1" stopColor="#eef4fb" />
            </linearGradient>
            <linearGradient id="rkRail" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="#e3ebf5" />
              <stop offset="0.5" stopColor="#f8fafc" />
              <stop offset="1" stopColor="#dce6f2" />
            </linearGradient>
            <linearGradient id="rkDev" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#ffffff" />
              <stop offset="1" stopColor="#f8fafc" />
            </linearGradient>
            <linearGradient id="rkInner" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#ffffff" />
              <stop offset="1" stopColor="#f6f9fd" />
            </linearGradient>
            <filter id="rkSoftShadow" x="-30%" y="-30%" width="160%" height="160%">
              <feDropShadow dx="0" dy="9" stdDeviation="9" floodColor="#1f334f" floodOpacity="0.08" />
            </filter>
          </defs>

          {/* 机柜外框 */}
          <rect x={FRAME_X - 6} y={RACK_TOP - 6} width={FRAME_W + 12} height={u * uPx + 12}
            rx={16} fill="url(#rkFrame)" stroke="rgba(43,63,96,0.10)" strokeWidth={0.9} filter="url(#rkSoftShadow)" />
          <rect x={INNER_X} y={RACK_TOP - 2} width={INNER_W} height={u * uPx + 4}
            rx={9} fill="url(#rkInner)" stroke="rgba(43,63,96,0.10)" strokeWidth={0.85} />
          <rect x={DEV_X} y={RACK_TOP - 7} width={DEV_W} height={2}
            rx={2} fill="rgba(43, 63, 96, 0.12)" />
          <rect x={DEV_X} y={RACK_TOP + u * uPx + 7} width={DEV_W} height={2}
            rx={2} fill="rgba(43, 63, 96, 0.12)" />

          {/* 立柱导轨 + U 孔 */}
          <rect x={INNER_X} y={RACK_TOP} width={10} height={u * uPx} rx={3} fill="url(#rkRail)" opacity={0.78} />
          <rect x={INNER_X + INNER_W - 10} y={RACK_TOP} width={10} height={u * uPx} rx={3} fill="url(#rkRail)" opacity={0.78} />
          {Array.from({ length: u + 1 }).map((_, i) => (
            <line key={`line${i}`} x1={DEV_X} x2={DEV_X + DEV_W} y1={RACK_TOP + i * uPx} y2={RACK_TOP + i * uPx}
              stroke="rgba(43,63,96,0.075)" />
          ))}
          {Array.from({ length: u }).map((_, i) => (
            <g key={`h${i}`}>
              <circle cx={INNER_X + 5} cy={RACK_TOP + i * uPx + uPx / 2} r={0.95} fill="#9aa7bd" opacity={0.42} />
              <circle cx={INNER_X + INNER_W - 5} cy={RACK_TOP + i * uPx + uPx / 2} r={0.95} fill="#9aa7bd" opacity={0.42} />
            </g>
          ))}

          {/* U 标尺 */}
          {ruler.map((n) => (
            <text key={`u${n}`} x={FRAME_X - 12} y={yFor(n, 1) + uPx / 2 + 3}
              textAnchor="end" fontSize={10} fill={TECH.textDim}
              style={{ fontFamily: 'ui-monospace, monospace' }}>{n}</text>
          ))}

          {/* 设备 */}
          {data.placed.map((d) => {
            const y = yFor(d.rack_u_start, d.u_size);
            const bad = d.overflow || overlapIds.has(d.inst_id);
            const conflicted = overlapIds.has(d.inst_id);
            const l = lane[d.inst_id] || 0;
            const dx = conflicted ? DEV_X + (l % 2) * (DEV_W / 2) : DEV_X;
            const wDev = conflicted ? DEV_W / 2 - 2 : DEV_W;
            const tx = dx + 22;
            const c = deviceColor(d.model_id);
            const h = Math.max(d.u_size * uPx - 3, 8);
            const cy = y + h / 2;
            const lim = Math.max(5, Math.floor((wDev - 38) / 6.6));
            const clip = (s: string) => (s.length > lim ? `${s.slice(0, lim - 1)}…` : s);
            const twoLine = h > 30;
            return (
              <g key={d.inst_id} className="rk-dev" style={{ cursor: 'pointer' }}
                onClick={() => onDevice(d)}>
                <rect x={dx} y={y + 1.5} width={wDev} height={h} rx={6}
                  fill="url(#rkDev)" stroke={bad ? TECH.danger : 'rgba(23,54,106,0.18)'}
                  strokeWidth={bad ? 1.5 : 0.8} />
                <rect x={dx + 5} y={y + 4} width={wDev - 10} height={Math.max(3, h * 0.28)} rx={5}
                  fill="rgba(255,255,255,0.46)" />
                <circle cx={dx + 12} cy={cy} r={3.4} fill={bad ? TECH.danger : c} opacity={0.16} />
                <circle cx={dx + 12} cy={cy} r={1.9} fill={bad ? TECH.danger : c} />
                <text x={tx} y={cy - (twoLine ? 4 : -3.5)} fontSize={11}
                  fill={TECH.text} dominantBaseline="middle">{clip(d.inst_name)}</text>
                {twoLine && (
                  <text x={tx} y={cy + 9} fontSize={9.5} fill={TECH.textDim}>
                    {clip(`${deviceTypeName(d.model_id)} · U${d.rack_u_start}-${d.u_end}`)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {data.overlaps.length > 0 && (
        <Alert className="rk-alert" banner type="error" showIcon
          message={t('Model.rackUConflict')} />
      )}
      {data.unplaced.length > 0 && (
        <Alert className="rk-alert" banner type="warning" showIcon
          message={`${t('Model.rackUnplaced')}: ${data.unplaced.map((d) => d.inst_name).join('、')}`} />
      )}

      <style jsx>{`
        .rk-wrap {
          border-radius: ${embedded ? '0' : '10px'};
          border: ${embedded ? 'none' : `1px solid ${TECH.line}`};
          display: flex; flex-direction: column;
          overflow: hidden;
          box-shadow: ${embedded ? 'none' : '0 18px 42px rgba(31, 47, 75, 0.07)'};
          ${embedded ? '' : 'max-width: 420px; margin: 12px auto;'}
        }
        .rk-scroll {
          flex: 1;
          padding: 13px 8px 14px;
          background:
            linear-gradient(90deg, rgba(58, 83, 125, 0.055) 1px, transparent 1px),
            linear-gradient(0deg, rgba(58, 83, 125, 0.055) 1px, transparent 1px),
            #f6f9fd;
          background-size: 28px 28px;
        }
        .rk-ov {
          display: flex; gap: 8px; padding: 10px 14px;
          border-bottom: 1px solid ${TECH.line};
          background: #ffffff;
        }
        .rk-ov-i {
          flex: 1; display: flex; flex-direction: column; align-items: center;
          gap: 2px; padding: 7px 4px; border-radius: 8px;
          background: #f8fafc; border: 1px solid ${TECH.line};
        }
        .rk-ov-i :global(b) { font-size: 17px; font-weight: 760; color: ${TECH.text};
          font-family: ui-monospace, monospace; line-height: 1.1; }
        .rk-ov-i :global(i) { font-size: 11px; color: ${TECH.textDim}; font-style: normal; }
        .rk-ov-i.hl { background: rgba(43,101,217,0.08); border-color: rgba(43,101,217,0.32); }
        .rk-ov-i.hl :global(b) { color: ${TECH.cyan}; }
        .rk-dev :global(rect),
        .rk-dev :global(text) { transition: fill .15s ease, stroke .15s ease; }
        .rk-dev:hover :global(text) { fill: ${TECH.cyan}; }
        .rk-alert {
          margin: 10px 12px 12px;
          border-radius: 8px;
        }
      `}</style>
    </div>
  );
};

export default RackElevation;
