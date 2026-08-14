'use client';

import React, { useEffect, useState } from 'react';
import { Drawer, Spin, Button, Tag, Modal, message } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import { useCommon } from '@/app/cmdb/context/common';
import { useInstanceApi, useModelApi } from '@/app/cmdb/api';
import { getOrganizationDisplayText } from '@/app/cmdb/components/cmdb-shared';
import type { RackDevice } from '@/app/cmdb/types/rackRoom';
import type { UserItem } from '@/app/cmdb/types/assetManage';
import { deviceColor, deviceTypeName, TECH } from '@/app/cmdb/utils/rackRoomLayout';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import {
  buildDeviceDrawerRows,
  buildUnplacePayload,
  formatDeviceAttrDisplay,
  normalizeModelAttrList,
  type DeviceDrawerAttr,
} from './rackRoomEdit';

interface Props {
  device: RackDevice | null;
  open: boolean;
  onClose: () => void;
  containerInstUuid?: string;
  canUnplace?: boolean;
  onUnplaced?: () => void;
}

const DeviceDetailDrawer: React.FC<Props> = ({
  device,
  open,
  onClose,
  containerInstUuid,
  canUnplace,
  onUnplaced,
}) => {
  const { t } = useTranslation();
  const router = useRouter();
  const { getInstanceDetail, saveRackRoomLayout } = useInstanceApi();
  const { getModelAttrList } = useModelApi();
  const { flatGroups } = useUserInfoContext();
  const userList: UserItem[] = useCommon()?.userList || [];
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [attrs, setAttrs] = useState<DeviceDrawerAttr[]>([]);

  useEffect(() => {
    if (!open || !device) return;
    let cancelled = false;
    setLoading(true);
    setDetail(null);
    setAttrs([]);
    const instUuid = device.inst_uuid;
    Promise.all([
      instUuid ? getInstanceDetail(instUuid).catch(() => null) : Promise.resolve(null),
      getModelAttrList(device.model_id).catch(() => []),
    ])
      .then(([d, a]) => {
        if (cancelled) return;
        setDetail((d as Record<string, unknown>) || null);
        setAttrs(normalizeModelAttrList(a));
      })
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
     
  }, [open, device?.inst_uuid, device?.inst_id]);

  const jump = () => {
    if (!device) return;
    const params = new URLSearchParams({
      icn: '', model_name: device.model_id, model_id: device.model_id,
      classification_id: '', inst_uuid: device.inst_uuid || device.inst_id, inst_name: device.inst_name,
    }).toString();
    router.push(`/cmdb/assetData/detail/baseInfo?${params}`);
  };

  const confirmUnplace = () => {
    if (!device || !containerInstUuid || !canUnplace) return;
    Modal.confirm({
      centered: true,
      title: t('Model.layoutUnplaceConfirmTitle'),
      content: t('Model.layoutUnplaceDeviceContent'),
      okButtonProps: { danger: true },
      onOk: async () => {
        await saveRackRoomLayout(
          buildUnplacePayload({
            scope: 'rack',
            containerInstUuid,
            instUuid: device.inst_uuid || device.inst_id,
          })
        );
        message.success(t('successfullyDisassociated'));
        onClose();
        onUnplaced?.();
      },
    });
  };

  const c = device ? deviceColor(device.model_id) : TECH.cyan;
  const displayRecord: Record<string, unknown> = {
    ...(device as unknown as Record<string, unknown>),
    ...(detail || {}),
  };
  const formatReadonly = (attr: DeviceDrawerAttr, raw: unknown): string => {
    if (attr.attr_type === 'organization' || attr.attr_id === 'organization') {
      return getOrganizationDisplayText(
        raw as string | number | Array<string | number>,
        flatGroups || []
      ) || '--';
    }
    if (attr.attr_type === 'user') {
      const ids = Array.isArray(raw) ? raw : raw ? [raw] : [];
      const names = ids.map((id) => {
        const user = userList.find((item) => String(item.id) === String(id));
        return user ? String(user.display_name || user.username || id) : String(id);
      });
      return names.filter(Boolean).join('、') || '--';
    }
    return formatDeviceAttrDisplay(attr, raw, {
      empty: '--',
      yes: t('common.yes', '是'),
      no: t('common.no', '否'),
    });
  };
  const rows = buildDeviceDrawerRows({
    attrs,
    detail: displayRecord,
    formatValue: formatReadonly,
  });

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={500}
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
            <span
              className="dd-led"
              style={{ background: c, boxShadow: `0 0 10px ${c}` }}
            />
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="dd-name" title={device.inst_name}>
                {device.inst_name}
              </div>
              <div className="dd-sub">
                <Tag
                  style={{
                    background: 'transparent',
                    borderColor: c,
                    color: c,
                    margin: 0,
                  }}
                >
                  {deviceTypeName(device.model_id)}
                </Tag>
                <span className="dd-u">
                  U{device.rack_u_start}-{device.u_end} · {device.u_size}U
                </span>
              </div>
            </div>
          </div>

          <div className="dd-body">
            {loading ? (
              <div style={{ padding: 40, textAlign: 'center' }}>
                <Spin spinning />
              </div>
            ) : rows.length ? (
              <div className="dd-grid">
                {rows.map((row) => (
                  <div className="dd-row" key={row.key}>
                    <EllipsisWithTooltip text={row.label} className="dd-k" />
                    <EllipsisWithTooltip text={row.value} className="dd-v" />
                  </div>
                ))}
              </div>
            ) : (
              <div className="dd-empty">{t('Model.deviceDrawerLoadFailed')}</div>
            )}
          </div>

          <div className="dd-ft">
            {canUnplace && containerInstUuid && (
              <Button danger block onClick={confirmUnplace} style={{ marginBottom: 8 }}>
                {t('Model.layoutUnplace')}
              </Button>
            )}
            <Button type="primary" block onClick={jump}>
              {t('Model.viewFullInstance')} <ArrowRightOutlined />
            </Button>
          </div>
        </div>
      )}

      <style jsx>{`
        .dd {
          display: flex;
          flex-direction: column;
          height: 100%;
          color: ${TECH.text};
        }
        .dd-hd {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 18px 20px;
          background: linear-gradient(180deg, ${TECH.panelHi}, ${TECH.bg0});
          border-bottom: 1px solid ${TECH.line};
        }
        .dd-led {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          flex: none;
        }
        .dd-name {
          font-size: 16px;
          font-weight: 600;
          color: ${TECH.text};
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .dd-sub {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-top: 6px;
        }
        .dd-u {
          font-size: 12px;
          color: ${TECH.textDim};
          font-family: ui-monospace, monospace;
        }
        .dd-body {
          flex: 1;
          overflow: auto;
          padding: 8px 14px;
        }
        .dd-grid {
          display: flex;
          flex-direction: column;
        }
        .dd-row {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          gap: 14px;
          padding: 11px 6px;
          border-bottom: 1px dashed ${TECH.line};
        }
        .dd-row :global(.dd-k) {
          color: ${TECH.textDim};
          font-size: 13px;
          flex: none;
          max-width: 42%;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .dd-row :global(.dd-v) {
          color: ${TECH.text};
          font-size: 13px;
          flex: 1;
          min-width: 0;
          text-align: right;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .dd-empty {
          padding: 40px;
          text-align: center;
          color: ${TECH.textDim};
        }
        .dd-ft {
          padding: 14px 16px;
          border-top: 1px solid ${TECH.line};
        }
      `}</style>
    </Drawer>
  );
};

export default DeviceDetailDrawer;
