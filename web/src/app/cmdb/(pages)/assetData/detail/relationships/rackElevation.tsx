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

const FRAME_X = 52;
const FRAME_W = 214;
const DEV_X = FRAME_X + 8;
const DEV_W = FRAME_W - 16;
const SVG_W = FRAME_X + FRAME_W + 24;
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
      <div className="rk-scroll" ref={scrollRef} style={{ padding: '12px 8px 10px' }}>
        <svg width={SVG_W} height={svgH} style={{ display: 'block', margin: '0 auto' }}>
          <defs>
            <linearGradient id="rkFrame" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="#eef2f8" />
              <stop offset="0.5" stopColor="#e0e7f2" />
              <stop offset="1" stopColor="#eef2f8" />
            </linearGradient>
            <linearGradient id="rkRail" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="#d6dde9" />
              <stop offset="1" stopColor="#c3ccda" />
            </linearGradient>
            <linearGradient id="rkDev" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#fbfdff" />
              <stop offset="1" stopColor="#eaf0f8" />
            </linearGradient>
            <filter id="rkGlow" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="2.4" result="b" />
              <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          {/* 机柜外框 + 顶部呼吸光 */}
          <rect x={FRAME_X - 6} y={RACK_TOP - 6} width={FRAME_W + 12} height={u * uPx + 12}
            rx={10} fill="url(#rkFrame)" stroke={TECH.lineHi} strokeWidth={1.2} />
          <rect x={FRAME_X - 6} y={RACK_TOP - 6} width={FRAME_W + 12} height={3}
            rx={2} fill={TECH.cyan} opacity={0.7} filter="url(#rkGlow)" />

          {/* 立柱导轨 + U 孔 */}
          <rect x={FRAME_X} y={RACK_TOP} width={9} height={u * uPx} fill="url(#rkRail)" />
          <rect x={FRAME_X + FRAME_W - 9} y={RACK_TOP} width={9} height={u * uPx} fill="url(#rkRail)" />
          {Array.from({ length: u }).map((_, i) => (
            <g key={`h${i}`}>
              <circle cx={FRAME_X + 4.5} cy={RACK_TOP + i * uPx + uPx / 2} r={1.1} fill="#9aa7bd" />
              <circle cx={FRAME_X + FRAME_W - 4.5} cy={RACK_TOP + i * uPx + uPx / 2} r={1.1} fill="#9aa7bd" />
            </g>
          ))}

          {/* U 标尺 */}
          {ruler.map((n) => (
            <text key={`u${n}`} x={FRAME_X - 12} y={yFor(n, 1) + uPx - 3}
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
            const tx = dx + 12;
            const c = deviceColor(d.model_id);
            const h = Math.max(d.u_size * uPx - 3, 8);
            const cy = y + h / 2;
            const lim = Math.max(5, Math.floor((wDev - 24) / 6.6));
            const clip = (s: string) => (s.length > lim ? `${s.slice(0, lim - 1)}…` : s);
            const twoLine = h > 30;
            return (
              <g key={d.inst_id} className="rk-dev" style={{ cursor: 'pointer' }}
                onClick={() => onDevice(d)}>
                <rect x={dx} y={y + 1.5} width={wDev} height={h} rx={3}
                  fill="url(#rkDev)" stroke={bad ? TECH.danger : 'rgba(23,54,106,0.18)'}
                  strokeWidth={bad ? 1.6 : 0.8}
                  filter={bad ? 'url(#rkGlow)' : undefined} />
                <rect x={dx + 3} y={y + 4} width={3.5} height={Math.max(h - 5, 4)} rx={1.5}
                  fill={c} filter="url(#rkGlow)" />
                {h > 22 && !conflicted && [0, 1, 2].map((k) => (
                  <line key={k} x1={tx + 4} x2={tx + 58}
                    y1={cy - 4 + k * 4} y2={cy - 4 + k * 4}
                    stroke="rgba(23,54,106,0.12)" strokeWidth={1.4} />
                ))}
                <circle cx={dx + wDev - 9} cy={cy} r={2.1} fill={bad ? TECH.danger : TECH.ok}
                  filter="url(#rkGlow)" />
                {!conflicted && (
                  <circle cx={dx + wDev - 17} cy={cy} r={2.1} fill={TECH.cyan} opacity={0.8} />
                )}
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
          border-radius: ${embedded ? '0' : '12px'};
          border: ${embedded ? 'none' : `1px solid ${TECH.line}`};
          display: flex; flex-direction: column;
          ${embedded ? '' : 'max-width: 360px; margin: 12px auto;'}
        }
        .rk-scroll { flex: 1; }
        .rk-ov {
          display: flex; gap: 8px; padding: 12px 14px;
          border-bottom: 1px solid ${TECH.line};
          background: linear-gradient(180deg, ${TECH.panel}, ${TECH.bg1});
        }
        .rk-ov-i {
          flex: 1; display: flex; flex-direction: column; align-items: center;
          gap: 2px; padding: 6px 4px; border-radius: 8px;
          background: rgba(23,54,106,0.04); border: 1px solid ${TECH.line};
        }
        .rk-ov-i :global(b) { font-size: 17px; font-weight: 600; color: ${TECH.text};
          font-family: ui-monospace, monospace; line-height: 1.1; }
        .rk-ov-i :global(i) { font-size: 11px; color: ${TECH.textDim}; font-style: normal; }
        .rk-ov-i.hl { background: rgba(47,116,230,0.1); border-color: rgba(47,116,230,0.35); }
        .rk-ov-i.hl :global(b) { color: ${TECH.cyan}; }
        .rk-dev :global(rect) { transition: filter .15s; }
        .rk-dev:hover :global(text) { fill: ${TECH.cyan}; }
      `}</style>
    </div>
  );
};

export default RackElevation;
