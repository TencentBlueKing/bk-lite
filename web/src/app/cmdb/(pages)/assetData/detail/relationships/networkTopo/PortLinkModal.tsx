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
    if (!open || !sourceId || !targetId) return;
    setSrcPortId(undefined);
    setDstPortId(undefined);
    setCreatingSide(null);
    setSrcOccupied(new Set());
    setDstOccupied(new Set());
    setLoading(true);
    Promise.all([
      getAssociationInstanceList(sourceModel, sourceId).then((l: any) =>
        setSrcPorts(extractDevicePorts(l, sourceModel as string))
      ),
      getAssociationInstanceList(targetModel, targetId).then((l: any) =>
        setDstPorts(extractDevicePorts(l, targetModel as string))
      ),
      // 取各设备已占用端口（depth=1 拿该设备所有直连），用于下拉置灰
      getNetworkTopo(sourceModel as string, sourceId, 1)
        .then((d: any) => setSrcOccupied(extractOccupiedPortNames(d?.links, sourceId)))
        .catch(() => undefined),
      getNetworkTopo(targetModel as string, targetId, 1)
        .then((d: any) => setDstOccupied(extractOccupiedPortNames(d?.links, targetId)))
        .catch(() => undefined),
    ]).finally(() => setLoading(false));
    // 预取 interface 模型属性，供内联建端口
    getModelAttrList(INTERFACE_MODEL)
      .then(setInterfaceAttrs)
      .catch(() => setInterfaceAttrs([]));
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

  const renderSide = (
    side: 'src' | 'dst',
    ep: PortEndpoint | null,
    ports: PortOption[],
    value: string | undefined,
    onChange: (v: string) => void,
    occupied: Set<string>
  ) => (
    <div className="mb-4">
      <div className="mb-1 font-medium">{ep?.name}</div>
      {ports.length ? (
        <Select
          className="w-full"
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
        <div className="text-[var(--color-text-4)] text-sm">
          {t('Model.networkTopoNoPort')}
        </div>
      )}
      {creatingSide === side ? (
        <Form form={form} layout="vertical" className="mt-2 p-2 border rounded">
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
          <div className="flex gap-2">
            <Button
              type="primary"
              size="small"
              loading={submitting}
              onClick={() => handleCreatePort(side)}
            >
              {t('common.confirm')}
            </Button>
            <Button
              size="small"
              onClick={() => {
                setCreatingSide(null);
                form.resetFields();
              }}
            >
              {t('common.cancel')}
            </Button>
          </div>
        </Form>
      ) : (
        <Button
          type="link"
          size="small"
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
  );

  return (
    <Modal
      title={t('Model.networkTopoLinkTitle')}
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      confirmLoading={submitting}
      destroyOnClose
    >
      <Spin spinning={loading}>
        {renderSide('src', source, srcPorts, srcPortId, setSrcPortId, srcOccupied)}
        {renderSide('dst', target, dstPorts, dstPortId, setDstPortId, dstOccupied)}
      </Spin>
    </Modal>
  );
};

export default PortLinkModal;
