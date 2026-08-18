'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Col, Drawer, Form, Input, Row, Select, Spin, Tag, message } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useLocale } from '@/context/locale';
import { useRouter } from 'next/navigation';
import PermissionWrapper from '@/components/permission';
import { useInstanceApi, useModelApi } from '@/app/cmdb/api';
import { useUserInfoContext } from '@/context/userInfo';
import { useCommon } from '@/app/cmdb/context/common';
import { getOrganizationDisplayText } from '@/app/cmdb/components/cmdb-shared';
import { resolveCmdbInstUuid } from '@/app/cmdb/utils/instUuid';
import { KIND_COLOR, ipToCellKind, type CellKind, type IpInstance } from './ipamCells';
import {
  IPAM_ALLOC_ATTR_ID,
  IPAM_ASSET_PERMISSION_PATH,
  IPAM_AVAILABLE,
  IPAM_DESC_ATTR_ID,
  IPAM_MAC_ATTR_ID,
  IPAM_STATUS_ATTR_ID,
  IPAM_TYPE_ATTR_ID,
  IPAM_USER_ATTR_ID,
  buildIpamEditPayload,
  canPerformIpamEdit,
  decideManualIpAction,
  defaultAllocStatus,
  enumOptionsFromAttr,
  findModelAttr,
  firstEnum,
  formatAttrDisplay,
  hasInstanceOperate,
  isEditableIpAttr,
  isPersistedIp,
  listDrawerIpAttrs,
  type IpamEditPayload,
  type IpamModelAttr,
} from './ipamEdit';

interface IpDetailDrawerProps {
  ip: IpInstance | null;
  open: boolean;
  subnetInstUuid: string;
  hasAdd: boolean;
  hasEdit: boolean;
  hasDelete: boolean;
  saving?: boolean;
  onClose: () => void;
  onSave: (payload: IpamEditPayload) => Promise<void> | void;
}

type DraftValue = string | string[];

const IpDetailDrawer: React.FC<IpDetailDrawerProps> = ({
  ip,
  open,
  subnetInstUuid,
  hasAdd,
  hasEdit,
  hasDelete,
  saving = false,
  onClose,
  onSave,
}) => {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const isZh = locale.toLowerCase().startsWith('zh');
  const router = useRouter();
  const { getModelAttrList } = useModelApi();
  const { getInstanceDetail } = useInstanceApi();
  const { flatGroups } = useUserInfoContext();
  const userList = useCommon()?.userList || [];
  const [draft, setDraft] = useState<Record<string, DraftValue>>({});
  const [attrs, setAttrs] = useState<IpamModelAttr[]>([]);
  const [attrLoading, setAttrLoading] = useState(false);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const attrsLoadedRef = useRef(false);

  const persisted = isPersistedIp(ip);
  const instOperate = hasInstanceOperate(ip?.permission);
  const allocatedStatus = String(draft[IPAM_ALLOC_ATTR_ID] || '');
  const action = decideManualIpAction({
    hasInstance: persisted,
    allocatedStatus,
  });
  const canEditForm = persisted
    ? (hasEdit || hasDelete) && instOperate
    : hasAdd;
  const canSave =
    action !== 'noop' &&
    canPerformIpamEdit({
      action,
      hasAdd,
      hasEdit,
      hasDelete,
      instOperate,
    });

  const visibleAttrs = useMemo(() => listDrawerIpAttrs(attrs), [attrs]);
  const displayRecord = useMemo<Record<string, unknown>>(
    () => ({ ...(ip || {}), ...(detail || {}) }),
    [ip, detail]
  );

  useEffect(() => {
    if (!open || attrsLoadedRef.current) return;
    let cancelled = false;
    setAttrLoading(true);
    getModelAttrList('ip')
      .then((res: unknown) => {
        if (cancelled) return;
        setAttrs(Array.isArray(res) ? (res as IpamModelAttr[]) : []);
        attrsLoadedRef.current = true;
      })
      .catch(() => {
        if (!cancelled) setAttrs([]);
      })
      .finally(() => {
        if (!cancelled) setAttrLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open || !ip || !persisted) {
      setDetail(null);
      return;
    }
    const instUuid = resolveCmdbInstUuid(ip.inst_uuid);
    if (!instUuid) {
      setDetail(ip as Record<string, unknown>);
      return;
    }
    let cancelled = false;
    getInstanceDetail(instUuid)
      .then((res: unknown) => {
        if (cancelled) return;
        setDetail(res && typeof res === 'object' ? (res as Record<string, unknown>) : (ip as Record<string, unknown>));
      })
      .catch(() => {
        if (!cancelled) setDetail(ip as Record<string, unknown>);
      });
    return () => {
      cancelled = true;
    };
  }, [open, ip, persisted]);

  useEffect(() => {
    if (!open || !ip) return;
    const record = { ...ip, ...(detail || {}) } as Record<string, unknown>;
    const allocOptions = enumOptionsFromAttr(findModelAttr(attrs, IPAM_ALLOC_ATTR_ID));
    const currentAlloc = firstEnum(record[IPAM_ALLOC_ATTR_ID]);
    setDraft({
      [IPAM_ALLOC_ATTR_ID]: currentAlloc || (persisted ? '' : defaultAllocStatus(allocOptions)),
      [IPAM_STATUS_ATTR_ID]: firstEnum(record[IPAM_STATUS_ATTR_ID]) || '',
      [IPAM_TYPE_ATTR_ID]: firstEnum(record[IPAM_TYPE_ATTR_ID]) || '',
      [IPAM_USER_ATTR_ID]: Array.isArray(record[IPAM_USER_ATTR_ID])
        ? (record[IPAM_USER_ATTR_ID] as unknown[]).map(String)
        : record[IPAM_USER_ATTR_ID]
          ? [String(record[IPAM_USER_ATTR_ID])]
          : [],
      [IPAM_MAC_ATTR_ID]: record[IPAM_MAC_ATTR_ID] == null ? '' : String(record[IPAM_MAC_ATTR_ID]),
      [IPAM_DESC_ATTR_ID]: record[IPAM_DESC_ATTR_ID] == null ? '' : String(record[IPAM_DESC_ATTR_ID]),
    });
  }, [open, ip, persisted, attrs, detail]);

  const kindLabel = useMemo<Record<CellKind, string>>(
    () => ({
      free: t('Model.ipViewFree'),
      allocated_online: t('Model.ipViewAllocatedOnline'),
      allocated_offline: t('Model.ipViewAllocatedOffline'),
      conflict: t('Model.ipViewConflict'),
      reserved: t('Model.ipViewReserved'),
      gateway: t('Model.ipViewGateway'),
      unknown: t('Model.ipViewUnknown'),
    }),
    [t]
  );

  const unallocateHint = t(
    'Model.ipViewUnallocateHint',
    isZh ? '改回可分配将删除该 IP 台账，格子恢复为空闲' : 'Setting this IP back to free deletes the record and returns the cell to unused'
  );

  if (!ip) return null;

  const kind = ipToCellKind(ip);
  const color = KIND_COLOR[persisted ? kind : 'free'];
  const savePermission =
    action === 'delete' ? ['Delete'] : persisted ? ['Edit'] : ['Add'];

  const patchDraft = (attrId: string, value: DraftValue) => {
    setDraft((prev) => ({ ...prev, [attrId]: value }));
  };

  const formatReadonly = (attr: IpamModelAttr): string => {
    const raw = displayRecord[attr.attr_id];
    if (attr.attr_type === 'organization') {
      return getOrganizationDisplayText(raw as string | number | Array<string | number>, flatGroups || []) || '--';
    }
    if (attr.attr_type === 'user') {
      const ids = Array.isArray(raw) ? raw : raw ? [raw] : [];
      const names = ids.map((id) => {
        const user = userList.find((item) => String(item.id) === String(id));
        return user ? (user.display_name || user.username) : String(id);
      });
      return names.filter(Boolean).join('、') || '--';
    }
    return formatAttrDisplay(attr, raw, {
      empty: '--',
      yes: t('common.yes', '是'),
      no: t('common.no', '否'),
    });
  };

  const renderEditor = (attr: IpamModelAttr) => {
    const options = enumOptionsFromAttr(attr);
    const reverting = persisted && allocatedStatus === IPAM_AVAILABLE;
    const disabled = !canEditForm || (reverting && attr.attr_id !== IPAM_ALLOC_ATTR_ID);
    const isMultiLine =
      attr.attr_id === IPAM_DESC_ATTR_ID ||
      (attr.attr_type === 'str' &&
        Boolean(attr.option && typeof attr.option === 'object' && (attr.option as { widget_type?: string }).widget_type === 'multi_line'));
    if (attr.attr_type === 'enum' || options.length > 0) {
      return (
        <Select
          value={(draft[attr.attr_id] as string) || undefined}
          disabled={disabled}
          allowClear={attr.attr_id !== IPAM_ALLOC_ATTR_ID}
          placeholder={t('common.selectTip', isZh ? '请选择' : 'Select')}
          options={options.map((item) => ({
            value: item.id,
            label: item.name,
            disabled:
              attr.attr_id === IPAM_ALLOC_ATTR_ID && item.id === IPAM_AVAILABLE
                ? persisted && !hasDelete
                : false,
          }))}
          onChange={(value) => patchDraft(attr.attr_id, value || '')}
          className="w-full"
        />
      );
    }
    if (attr.attr_type === 'user') {
      return (
        <Select
          mode="multiple"
          value={(draft[attr.attr_id] as string[]) || []}
          disabled={disabled}
          showSearch
          optionFilterProp="label"
          placeholder={t('common.selectTip', isZh ? '请选择' : 'Select')}
          options={userList.map((user) => ({
            value: String(user.id),
            label: `${user.display_name || user.username}(${user.username})`,
          }))}
          onChange={(value) => patchDraft(attr.attr_id, value)}
          className="w-full"
        />
      );
    }
    if (isMultiLine) {
      return (
        <Input.TextArea
          rows={3}
          maxLength={200}
          value={String(draft[attr.attr_id] ?? '')}
          disabled={disabled}
          onChange={(event) => patchDraft(attr.attr_id, event.target.value)}
        />
      );
    }
    return (
      <Input
        value={String(draft[attr.attr_id] ?? '')}
        disabled={disabled}
        onChange={(event) => patchDraft(attr.attr_id, event.target.value)}
      />
    );
  };

  const jump = () => {
    const instUuid = resolveCmdbInstUuid(ip.inst_uuid);
    if (!instUuid) {
      message.warning('实例缺少合法 inst_uuid，请先完成 UUID 存量清洗');
      return;
    }
    const params = new URLSearchParams({
      icn: '',
      model_name: 'ip',
      model_id: 'ip',
      classification_id: '',
      inst_uuid: instUuid,
      inst_name: ip.ip_addr,
    }).toString();
    router.push(`/cmdb/assetData/detail/baseInfo?${params}`);
  };

  const handleSave = () => {
    void onSave(
      buildIpamEditPayload({
        subnetInstUuid,
        ipAddr: ip.ip_addr,
        allocatedStatus,
        ipStatus: String(draft[IPAM_STATUS_ATTR_ID] || ''),
        ipType: String(draft[IPAM_TYPE_ATTR_ID] || ''),
        ipUser: Array.isArray(draft[IPAM_USER_ATTR_ID]) ? (draft[IPAM_USER_ATTR_ID] as string[]) : [],
        mac: String(draft[IPAM_MAC_ATTR_ID] || ''),
        description: String(draft[IPAM_DESC_ATTR_ID] || ''),
      })
    );
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={680}
      title={
        <span className="inline-flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ background: color }}
          />
          {ip.ip_addr}
        </span>
      }
      extra={
        persisted ? (
          <Button size="small" icon={<ArrowRightOutlined />} onClick={jump}>
            {t('Model.viewFullInstance')}
          </Button>
        ) : null
      }
      footer={
        canEditForm ? (
          <div className="flex justify-end gap-2">
            <Button onClick={onClose}>{t('common.cancel')}</Button>
            <PermissionWrapper
              requiredPermissions={savePermission}
              permissionPath={IPAM_ASSET_PERMISSION_PATH}
              instPermissions={persisted ? ip.permission : ['Operate']}
            >
              <Button type="primary" loading={saving} disabled={!canSave} onClick={handleSave}>
                {t('common.save')}
              </Button>
            </PermissionWrapper>
          </div>
        ) : null
      }
    >
      <div className="mb-4">
        <Tag color={color} className="text-white">
          {persisted ? kindLabel[kind] : t('Model.ipViewFree')}
        </Tag>
      </div>
      {attrLoading && attrs.length === 0 ? (
        <div className="py-6 text-center">
          <Spin />
        </div>
      ) : (
        <Form layout="vertical">
          <Row gutter={24}>
            {visibleAttrs.map((attr) => {
              const editable = isEditableIpAttr(attr.attr_id);
              return (
                <Col span={12} key={attr.attr_id}>
                  <Form.Item
                    className="mb-4"
                    label={attr.attr_name || attr.attr_id}
                    required={attr.attr_id === IPAM_ALLOC_ATTR_ID}
                  >
                    {editable ? renderEditor(attr) : (
                      <div className="min-h-[22px] break-all text-[var(--color-text-1)]">
                        {formatReadonly(attr)}
                      </div>
                    )}
                  </Form.Item>
                </Col>
              );
            })}
          </Row>
          {persisted && allocatedStatus === IPAM_AVAILABLE ? (
            <div className="text-xs text-[var(--color-text-3)]">
              {unallocateHint}
            </div>
          ) : null}
        </Form>
      )}
    </Drawer>
  );
};

export default IpDetailDrawer;
