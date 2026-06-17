'use client';

import React, { useEffect, useState } from 'react';
import { Drawer, Spin, Button, Tag } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi, useModelApi } from '@/app/cmdb/api';
import type { RackDevice } from '@/app/cmdb/types/rackRoom';
import { deviceColor, deviceTypeName, TECH } from '@/app/cmdb/utils/rackRoomLayout';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

interface Props {
  device: RackDevice | null;
  open: boolean;
  onClose: () => void;
}

interface AttrDef {
  attr_id: string;
  attr_name: string;
  attr_type?: string;
  option?: Array<{ id: string | number; name: string }>;
}

const SKIP = new Set(['inst_name', 'organization', 'rack_u_start', 'u_size']);

const fmtValue = (attr: AttrDef, raw: unknown): string => {
  if (raw === null || raw === undefined || raw === '') return '--';
  // 枚举：把存储的 id（可能是列表）映射成中文名
  if (attr.attr_type === 'enum' && Array.isArray(attr.option)) {
    const ids = Array.isArray(raw) ? raw : [raw];
    const names = ids.map((v) => {
      const hit = attr.option!.find((o) => String(o.id) === String(v));
      return hit ? hit.name : String(v);
    });
    return names.length ? names.join('、') : '--';
  }
  if (Array.isArray(raw)) return raw.length ? raw.join('、') : '--';
  if (typeof raw === 'object') return JSON.stringify(raw);
  return String(raw);
};

const DeviceDetailDrawer: React.FC<Props> = ({ device, open, onClose }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const { getInstanceDetail } = useInstanceApi();
  const { getModelAttrList } = useModelApi();
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [attrs, setAttrs] = useState<AttrDef[]>([]);

  useEffect(() => {
    if (!open || !device) return;
    let cancelled = false;
    setLoading(true);
    setDetail(null);
    setAttrs([]);
    Promise.all([
      getInstanceDetail(device.inst_id).catch(() => null),
      getModelAttrList(device.model_id).catch(() => []),
    ])
      .then(([d, a]) => {
        if (cancelled) return;
        setDetail((d as Record<string, unknown>) || null);
        setAttrs(Array.isArray(a) ? (a as AttrDef[]) : []);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, device?.inst_id]);

  const jump = () => {
    if (!device) return;
    const params = new URLSearchParams({
      icn: '', model_name: device.model_id, model_id: device.model_id,
      classification_id: '', inst_id: device.inst_id, inst_name: device.inst_name,
    }).toString();
    router.push(`/cmdb/assetData/detail/baseInfo?${params}`);
  };

  const c = device ? deviceColor(device.model_id) : TECH.cyan;

  // 优先按模型属性顺序渲染（中文名 + 枚举解析）；无属性定义时回退到原始键值
  const rows: Array<{ k: string; v: string }> = [];
  if (detail) {
    if (attrs.length) {
      attrs.forEach((a) => {
        if (SKIP.has(a.attr_id)) return;
        const raw = detail[a.attr_id];
        if (raw === null || raw === undefined || raw === '' ||
          (Array.isArray(raw) && raw.length === 0)) return;
        rows.push({ k: a.attr_name || a.attr_id, v: fmtValue(a, raw) });
      });
    } else {
      Object.entries(detail).forEach(([k, v]) => {
        if (SKIP.has(k) || k.startsWith('_') || v === null || v === '' ||
          (Array.isArray(v) && v.length === 0)) return;
        rows.push({ k, v: fmtValue({ attr_id: k, attr_name: k }, v) });
      });
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={400}
      zIndex={1080}
      title={null}
      closable={false}
      styles={{
        body: { padding: 0, background: TECH.bg0 },
        content: { background: TECH.bg0 },
        wrapper: { boxShadow: '-12px 0 40px rgba(23,54,106,0.15)' },
      }}
    >
      {device && (
        <div className="dd">
          <div className="dd-hd">
            <span className="dd-led" style={{ background: c, boxShadow: `0 0 10px ${c}` }} />
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="dd-name" title={device.inst_name}>{device.inst_name}</div>
              <div className="dd-sub">
                <Tag style={{ background: 'transparent', borderColor: c, color: c, margin: 0 }}>
                  {deviceTypeName(device.model_id)}
                </Tag>
                <span className="dd-u">U{device.rack_u_start}-{device.u_end} · {device.u_size}U</span>
              </div>
            </div>
          </div>

          <div className="dd-body">
            {loading ? (
              <div style={{ padding: 40, textAlign: 'center' }}><Spin spinning /></div>
            ) : rows.length ? (
              <div className="dd-grid">
                {rows.map((row) => (
                  <div className="dd-row" key={row.k}>
                    <EllipsisWithTooltip text={row.k} className="dd-k" />
                    <EllipsisWithTooltip text={row.v} className="dd-v" />
                  </div>
                ))}
              </div>
            ) : (
              <div className="dd-empty">{t('Model.noRackLayout')}</div>
            )}
          </div>

          <div className="dd-ft">
            <Button type="primary" block onClick={jump}>
              {t('Model.viewFullInstance')} <ArrowRightOutlined />
            </Button>
          </div>
        </div>
      )}

      <style jsx>{`
        .dd { display: flex; flex-direction: column; height: 100%; color: ${TECH.text}; }
        .dd-hd {
          display: flex; align-items: center; gap: 12px; padding: 18px 20px;
          background: linear-gradient(180deg, ${TECH.panelHi}, ${TECH.bg0});
          border-bottom: 1px solid ${TECH.line};
        }
        .dd-led { width: 10px; height: 10px; border-radius: 50%; flex: none; }
        .dd-name { font-size: 16px; font-weight: 600; color: ${TECH.text};
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .dd-sub { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
        .dd-u { font-size: 12px; color: ${TECH.textDim}; font-family: ui-monospace, monospace; }
        .dd-body { flex: 1; overflow: auto; padding: 8px 14px; }
        .dd-grid { display: flex; flex-direction: column; }
        .dd-row { display: flex; justify-content: space-between; align-items: baseline;
          gap: 14px; padding: 11px 6px; border-bottom: 1px dashed ${TECH.line}; }
        .dd-row :global(.dd-k) { color: ${TECH.textDim}; font-size: 13px;
          flex: none; max-width: 42%;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .dd-row :global(.dd-v) { color: ${TECH.text}; font-size: 13px;
          flex: 1; min-width: 0; text-align: right;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .dd-empty { padding: 40px; text-align: center; color: ${TECH.textDim}; }
        .dd-ft { padding: 14px 16px; border-top: 1px solid ${TECH.line}; }
      `}</style>
    </Drawer>
  );
};

export default DeviceDetailDrawer;
