'use client';

import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import { Button, Input, List, Modal, Radio, Select, Spin, message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi, useModelApi } from '@/app/cmdb/api';
import { useCommon } from '@/app/cmdb/context/common';
import type { UserItem, FieldModalRef } from '@/app/cmdb/types/assetManage';
import FieldModal from '../../list/fieldModal';
import { deviceTypeName } from '@/app/cmdb/utils/rackRoomLayout';
import {
  CANDIDATE_OCCUPIED,
  DEVICE_LOCKED_ATTR_IDS,
  PLACEABLE_DEVICE_MODELS,
  RACK_LOCKED_ATTR_IDS,
  buildPlaceCreatePayload,
  buildPlaceExistingPayload,
  candidateIsSelectable,
  candidateOpensDetail,
  formatRackLocationLabel,
  hasInstanceOperate,
  normalizeDeviceUSize,
  openInstanceDetail,
} from './rackRoomEdit';

export interface LayoutPlaceTarget {
  scope: 'room' | 'rack';
  containerInstUuid: string;
  row?: number;
  col?: number;
  uStart?: number;
}

export interface LayoutPlaceModalRef {
  show: (target: LayoutPlaceTarget) => void;
}

interface Props {
  hasAdd: boolean;
  hasEdit: boolean;
  onPlaced: () => void;
}

interface LayoutCandidate {
  inst_uuid: string;
  inst_name: string;
  model_id: string;
  status: string;
  u_size?: number;
  permission?: string[];
}

const LayoutPlaceModal = forwardRef<LayoutPlaceModalRef, Props>(
  ({ hasAdd, hasEdit, onPlaced }, ref) => {
    const { t } = useTranslation();
    const { saveRackRoomLayout, getRackRoomLayoutCandidates } = useInstanceApi();
    const { getModelAttrGroupsFullInfo } = useModelApi();
    const userList: UserItem[] = useCommon()?.userList || [];
    const fieldRef = useRef<FieldModalRef>(null);
    const [open, setOpen] = useState(false);
    const [mode, setMode] = useState<'create' | 'existing'>('create');
    const [target, setTarget] = useState<LayoutPlaceTarget | null>(null);
    const [modelId, setModelId] = useState('rack');
    const [search, setSearch] = useState('');
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [items, setItems] = useState<LayoutCandidate[]>([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);

    const locationLabel =
      target?.scope === 'room' && target.row && target.col
        ? formatRackLocationLabel(target.row, target.col)
        : target?.uStart
          ? `U${target.uStart}`
          : '';

    useImperativeHandle(ref, () => ({
      show: (next) => {
        setTarget(next);
        setModelId(next.scope === 'room' ? 'rack' : PLACEABLE_DEVICE_MODELS[0]);
        setMode(hasAdd ? 'create' : 'existing');
        setSearch('');
        setPage(1);
        setItems([]);
        setOpen(true);
      },
    }));

    const loadCandidates = useCallback(async () => {
      if (!open || !target || mode !== 'existing' || !hasEdit) return;
      setLoading(true);
      try {
        const res = await getRackRoomLayoutCandidates({
          scope: target.scope,
          container_inst_uuid: target.containerInstUuid,
          model_id: modelId,
          page,
          page_size: 20,
          search,
        });
        setItems(res?.items || []);
        setTotal(res?.count || 0);
      } catch {
        setItems([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    }, [open, target, mode, hasEdit, modelId, page, search]);

    useEffect(() => {
      loadCandidates();
    }, [loadCandidates]);

    const close = () => {
      setOpen(false);
      setTarget(null);
    };

    const openCreateForm = async () => {
      if (!target) return;
      if (target.scope === 'rack' && !modelId) {
        message.warning(t('Model.layoutSelectDeviceModel'));
        return;
      }
      try {
        const res = await getModelAttrGroupsFullInfo(modelId);
        const formInfo: Record<string, unknown> = {};
        if (target.scope === 'room' && target.row && target.col) {
          formInfo.location = formatRackLocationLabel(target.row, target.col);
        }
        if (target.scope === 'rack' && target.uStart) {
          formInfo.rack_u_start = target.uStart;
          formInfo.u_size = 1;
        }
        fieldRef.current?.showModal({
          title: t('common.addNew'),
          type: 'add',
          source: 'create',
          attrList: res?.groups || [],
          formInfo,
          subTitle: locationLabel,
          model_id: modelId,
          list: [],
          lockedAttrIds: [
            ...(target.scope === 'room' ? RACK_LOCKED_ATTR_IDS : DEVICE_LOCKED_ATTR_IDS),
          ],
          hideAssociate: true,
        });
      } catch {
        message.error(t('common.loadFailed'));
      }
    };

    const handleCreate = async (payload: {
      model_id: string;
      instance_info: Record<string, unknown>;
    }) => {
      if (!target) return;
      const instanceInfo = { ...payload.instance_info };
      if (target.scope === 'room') {
        delete instanceInfo.row;
        delete instanceInfo.col;
      }
      return saveRackRoomLayout(
        buildPlaceCreatePayload({
          scope: target.scope,
          containerInstUuid: target.containerInstUuid,
          modelId: payload.model_id,
          instanceInfo,
          row: target.row,
          col: target.col,
          uStart: target.uStart,
          uSize: normalizeDeviceUSize(payload.instance_info.u_size, 1),
        })
      );
    };

    const placeExisting = async (item: LayoutCandidate) => {
      if (!target) return;
      if (candidateOpensDetail(item.status)) {
        openInstanceDetail({
          modelId: item.model_id,
          instUuid: item.inst_uuid,
          instName: item.inst_name,
        });
        return;
      }
      if (!candidateIsSelectable(item.status)) return;
      if (!hasInstanceOperate(item.permission)) {
        message.warning(t('Model.layoutNoOperate'));
        return;
      }
      setSaving(true);
      try {
        await saveRackRoomLayout(
          buildPlaceExistingPayload({
            scope: target.scope,
            containerInstUuid: target.containerInstUuid,
            instUuid: item.inst_uuid,
            row: target.row,
            col: target.col,
            uStart: target.uStart,
            uSize: normalizeDeviceUSize(item.u_size, 1),
          })
        );
        message.success(t('successfullyAdded'));
        close();
        onPlaced();
      } finally {
        setSaving(false);
      }
    };

    return (
      <>
        <Modal
          open={open}
          onCancel={close}
          title={
            target?.scope === 'room'
              ? `${t('Model.layoutPlaceRackTitle')} ${locationLabel}`
              : `${t('Model.layoutPlaceDeviceTitle')} ${locationLabel}`
          }
          footer={null}
          width={560}
          destroyOnHidden
        >
          {hasAdd && hasEdit && (
            <Radio.Group
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              style={{ marginBottom: 16 }}
            >
              <Radio.Button value="create">{t('Model.layoutPlaceCreate')}</Radio.Button>
              <Radio.Button value="existing">{t('Model.layoutPlaceExisting')}</Radio.Button>
            </Radio.Group>
          )}

          {target?.scope === 'rack' && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 8, color: 'var(--color-text-3)' }}>
                {t('Model.layoutSelectDeviceModel')}
              </div>
              <Select
                value={modelId}
                style={{ width: '100%' }}
                onChange={(value) => {
                  setModelId(value);
                  setPage(1);
                }}
                options={PLACEABLE_DEVICE_MODELS.map((id) => ({
                  value: id,
                  label: deviceTypeName(id),
                }))}
              />
            </div>
          )}

          {mode === 'create' && hasAdd && (
            <div>
              <p style={{ color: 'var(--color-text-3)', marginBottom: 16 }}>
                {target?.scope === 'room'
                  ? `${t('Model.layoutCreateRackHint')} ${locationLabel}`
                  : `${t('Model.layoutCreateDeviceHint')} ${locationLabel}`}
              </p>
              <Button type="primary" onClick={openCreateForm}>
                {t('Model.layoutFillAssetForm')}
              </Button>
            </div>
          )}

          {mode === 'existing' && hasEdit && (
            <div>
              <Input.Search
                allowClear
                placeholder={t('common.search')}
                onSearch={(value) => {
                  setSearch(value);
                  setPage(1);
                }}
                style={{ marginBottom: 12 }}
              />
              <Spin spinning={loading || saving}>
                <List
                  dataSource={items}
                  pagination={{
                    current: page,
                    total,
                    pageSize: 20,
                    size: 'small',
                    onChange: setPage,
                  }}
                  locale={{ emptyText: t('common.noData') }}
                  renderItem={(item) => {
                    const occupied = item.status === CANDIDATE_OCCUPIED;
                    return (
                      <List.Item
                        style={{
                          cursor: 'pointer',
                          opacity: occupied ? 0.55 : 1,
                          color: occupied ? 'var(--color-text-3)' : undefined,
                        }}
                        onClick={() => placeExisting(item)}
                      >
                        <div>
                          <div>{item.inst_name}</div>
                          {occupied && (
                            <div style={{ fontSize: 12, color: 'var(--color-text-4)' }}>
                              {t('Model.layoutOccupiedElsewhereHint')}
                            </div>
                          )}
                        </div>
                      </List.Item>
                    );
                  }}
                />
              </Spin>
            </div>
          )}
        </Modal>
        <FieldModal
          ref={fieldRef}
          userList={userList}
          createHandler={handleCreate}
          onSuccess={() => {
            close();
            onPlaced();
          }}
        />
      </>
    );
  }
);

LayoutPlaceModal.displayName = 'LayoutPlaceModal';
export default LayoutPlaceModal;
