'use client';
import React, { useEffect, useState } from 'react';
import { Modal, Select, Form, Button, message, Spin } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useInstanceApi, useModelApi } from '@/app/cmdb/api';
import { useCommon } from '@/app/cmdb/context/common';
import { getFieldItem } from '@/app/cmdb/utils/common';
import {
  extractDevicePorts,
  extractOccupiedPortNames,
  buildBelongPayload,
  INTERFACE_MODEL,
  type PortOption,
} from './topoEditingUtils';
import topoStyle from '../index.module.scss';

// 新建端口迷你表单里走选择框的字段类型（与实例表单一致），其余用输入框
const SELECT_LIKE_TYPES = ['user', 'enum', 'bool', 'time', 'organization'];

export interface PortEndpoint {
  id: string;
  name: string;
  model_id: string;
}

interface PortLinkModalProps {
  open: boolean;
  source: PortEndpoint | null;
  target: PortEndpoint | null;
  onCancel: () => void;
  onConfirm: (r: {
    sourcePortId: string;
    sourcePortName: string;
    targetPortId: string;
    targetPortName: string;
  }) => Promise<void> | void;
}

const PortLinkModal: React.FC<PortLinkModalProps> = ({
  open,
  source,
  target,
  onCancel,
  onConfirm,
}) => {
  const { t } = useTranslation();
  const {
    getAssociationInstanceList,
    getNetworkTopo,
    createInstance,
    createInstanceAssociation,
  } = useInstanceApi();
  const { getModelAttrList } = useModelApi();
  const common = useCommon();
  const userList = common?.userList || [];

  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [srcPorts, setSrcPorts] = useState<PortOption[]>([]);
  const [dstPorts, setDstPorts] = useState<PortOption[]>([]);
  const [srcPortId, setSrcPortId] = useState<string>();
  const [dstPortId, setDstPortId] = useState<string>();
  // 已被连线占用的端口名（按设备）：下拉里置灰不可选
  const [srcOccupied, setSrcOccupied] = useState<Set<string>>(new Set());
  const [dstOccupied, setDstOccupied] = useState<Set<string>>(new Set());

  // 内联建端口的迷你表单（每端独立）
  const [interfaceAttrs, setInterfaceAttrs] = useState<any[]>([]);
  const [creatingSide, setCreatingSide] = useState<'src' | 'dst' | null>(null);
  const [form] = Form.useForm();

  // 只依赖原始值：父级每次渲染都会传入新的 source/target 对象引用，
  // 若把对象/hook 函数放进依赖，effect 会每次渲染都执行 → setState → 再渲染 → 无限请求后端。
  const sourceId = source?.id;
  const sourceModel = source?.model_id;
  const targetId = target?.id;
  const targetModel = target?.model_id;

  useEffect(() => {
    if (open) return;
    setCreatingSide(null);
    form.resetFields();
  }, [open, form]);

  useEffect(() => {
    if (!open || !sourceId || !targetId) return;
    let cancelled = false;
    setSrcPortId(undefined);
    setDstPortId(undefined);
    setCreatingSide(null);
    setSrcOccupied(new Set());
    setDstOccupied(new Set());
    setLoading(true);
    const stopLoading = () => {
      if (!cancelled) setLoading(false);
    };
    const loadingFallback = window.setTimeout(stopLoading, 1600);
    Promise.allSettled([
      getAssociationInstanceList(sourceModel, sourceId).then((l: any) => {
        if (!cancelled) setSrcPorts(extractDevicePorts(l, sourceModel as string));
      }),
      getAssociationInstanceList(targetModel, targetId).then((l: any) => {
        if (!cancelled) setDstPorts(extractDevicePorts(l, targetModel as string));
      }),
      // 取各设备已占用端口（depth=1 拿该设备所有直连），用于下拉置灰
      getNetworkTopo(sourceModel as string, sourceId, 1)
        .then((d: any) => {
          if (!cancelled) setSrcOccupied(extractOccupiedPortNames(d?.links, sourceId));
        })
        .catch(() => undefined),
      getNetworkTopo(targetModel as string, targetId, 1)
        .then((d: any) => {
          if (!cancelled) setDstOccupied(extractOccupiedPortNames(d?.links, targetId));
        })
        .catch(() => undefined),
    ]).finally(() => {
      window.clearTimeout(loadingFallback);
      stopLoading();
    });
    // 预取 interface 模型属性，供内联建端口
    getModelAttrList(INTERFACE_MODEL)
      .then((attrs) => {
        if (!cancelled) setInterfaceAttrs(attrs);
      })
      .catch(() => {
        if (!cancelled) setInterfaceAttrs([]);
      });
    return () => {
      cancelled = true;
      window.clearTimeout(loadingFallback);
    };
    // getAssociationInstanceList/getNetworkTopo/getModelAttrList 行为稳定但每次渲染新引用，故不入依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, sourceId, sourceModel, targetId, targetModel]);

  // 仅渲染必填 + 常用选填（按 attr_id 命中），其余隐藏，避免迷你表单过长
  const COMMON_OPTIONAL = ['alias', 'ifIndex', 'if_index', 'description'];
  const miniFields = interfaceAttrs.filter(
    (a) => a.is_required || COMMON_OPTIONAL.includes(a.attr_id)
  );

  const handleCreatePort = async (side: 'src' | 'dst') => {
    const ep = side === 'src' ? source : target;
    if (!ep) return;
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      const created = await createInstance({
        model_id: INTERFACE_MODEL,
        instance_info: values,
      });
      const portId = String(created._id);
      // 同时建端口 -> 设备 belong 归属
      await createInstanceAssociation(
        buildBelongPayload(portId, ep.id, ep.model_id)
      );
      const portName = values.inst_name || portId;
      const opt = { id: portId, name: portName };
      if (side === 'src') {
        setSrcPorts((p) => [...p, opt]);
        setSrcPortId(portId);
      } else {
        setDstPorts((p) => [...p, opt]);
        setDstPortId(portId);
      }
      setCreatingSide(null);
      form.resetFields();
      message.success(t('successfullyAdded'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleOk = async () => {
    if (!srcPortId || !dstPortId) {
      message.warning(t('Model.networkTopoSelectBothPorts'));
      return;
    }
    setSubmitting(true);
    try {
      await onConfirm({
        sourcePortId: srcPortId,
        sourcePortName: srcPorts.find((p) => p.id === srcPortId)?.name || srcPortId,
        targetPortId: dstPortId,
        targetPortName: dstPorts.find((p) => p.id === dstPortId)?.name || dstPortId,
      });
    } finally {
      setSubmitting(false);
    }
  };

  const createEndpoint =
    creatingSide === 'src' ? source : creatingSide === 'dst' ? target : null;

  const closeCreateModal = () => {
    setCreatingSide(null);
    form.resetFields();
  };

  const handleCreateOk = () => {
    if (!creatingSide) return;
    handleCreatePort(creatingSide);
  };

  const renderSide = (
    side: 'src' | 'dst',
    ep: PortEndpoint | null,
    ports: PortOption[],
    value: string | undefined,
    onChange: (v: string) => void,
    occupied: Set<string>
  ) => (
    <section className={topoStyle.portEndpointCard}>
      <div className={topoStyle.portEndpointHeader}>
        <span className={topoStyle.portEndpointBadge}>
          {side === 'src' ? 'A' : 'B'}
        </span>
        <div className="min-w-0">
          <div className={`${topoStyle.portEndpointName} truncate`}>
            {ep?.name || '--'}
          </div>
          <div className={topoStyle.portEndpointMeta}>
            {side === 'src' ? '起点设备' : '目标设备'}
          </div>
        </div>
      </div>
      <div className={topoStyle.portEndpointBody}>
        <div className={topoStyle.portSelectRow}>
          {ports.length ? (
            <Select
              placeholder={t('Model.networkTopoSelectPort')}
              value={value}
              onChange={onChange}
              // 已有连线的端口置灰不可选，并在标签后标注「已连接」
              options={ports.map((p) => {
                const isOccupied = occupied.has(p.name);
                return {
                  value: p.id,
                  disabled: isOccupied,
                  label: isOccupied
                    ? `${p.name}（${t('Model.networkTopoPortConnected')}）`
                    : p.name,
                };
              })}
            />
          ) : (
            <div className={topoStyle.portEmpty}>
              {t('Model.networkTopoNoPort')}
            </div>
          )}
          {creatingSide !== side && (
            <Button
              type="link"
              size="small"
              className={topoStyle.portAddButton}
              icon={<PlusOutlined />}
              onClick={() => {
                form.resetFields();
                setCreatingSide(side);
              }}
            >
              {t('Model.networkTopoAddPort')}
            </Button>
          )}
        </div>
      </div>
    </section>
  );

  return (
    <>
      <Modal
        title={t('Model.networkTopoLinkTitle')}
        open={open}
        centered
        width={560}
        onCancel={onCancel}
        onOk={handleOk}
        confirmLoading={submitting}
        destroyOnHidden
      >
        <Spin spinning={loading}>
          <div className={topoStyle.portLinkBody}>
            {renderSide('src', source, srcPorts, srcPortId, setSrcPortId, srcOccupied)}
            {renderSide('dst', target, dstPorts, dstPortId, setDstPortId, dstOccupied)}
          </div>
        </Spin>
      </Modal>
      <Modal
        title={
          createEndpoint
            ? `${t('Model.networkTopoAddPort')} - ${createEndpoint.name}`
            : t('Model.networkTopoAddPort')
        }
        open={!!creatingSide}
        centered
        width={480}
        onCancel={closeCreateModal}
        onOk={handleCreateOk}
        confirmLoading={submitting}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" className={topoStyle.portCreateForm}>
          {miniFields.map((a) => (
            <Form.Item
              key={a.attr_id}
              name={a.attr_id}
              label={a.attr_name}
              // organization/user/enum 等走选择框，复用实例表单同一套字段渲染
              rules={
                a.is_required ? [{ required: true, message: `${a.attr_name}` }] : []
              }
            >
              {getFieldItem({
                fieldItem: a,
                userList,
                isEdit: true,
                placeholder: SELECT_LIKE_TYPES.includes(a.attr_type)
                  ? t('common.selectTip')
                  : t('common.inputTip'),
                inModal: true,
                modelId: INTERFACE_MODEL,
              })}
            </Form.Item>
          ))}
        </Form>
      </Modal>
    </>
  );
};

export default PortLinkModal;
