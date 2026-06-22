import type { NetworkTopoLink } from '@/app/cmdb/types/assetData';

export const INTERFACE_MODEL = 'interface';
export const CONNECT_ASST_ID = 'connect';
export const CONNECT_MODEL_ASST_ID = 'interface_connect_interface';
export const BELONG_ASST_ID = 'belong';

export interface PortOption {
  id: string;
  name: string;
}

// 从 interface 模型关联列表推导全部「网络设备模型」id
export const filterNetworkDeviceModels = (
  interfaceAssociations: Array<{
    asst_id?: string;
    src_model_id?: string;
    dst_model_id?: string;
  }>
): string[] => {
  const set = new Set<string>();
  (interfaceAssociations || []).forEach((a) => {
    if (
      a.asst_id === BELONG_ASST_ID &&
      a.src_model_id === INTERFACE_MODEL &&
      a.dst_model_id
    ) {
      set.add(a.dst_model_id);
    }
  });
  return Array.from(set);
};

export const isNetworkModel = (
  modelId: string,
  networkModels: string[]
): boolean => networkModels.includes(modelId);

// 从 getAssociationInstanceList 结果中取某设备的端口实例选项
export const extractDevicePorts = (
  assocList: Array<{
    model_asst_id?: string;
    inst_list?: Array<{ _id: string | number; inst_name: string }>;
  }>,
  deviceModel: string
): PortOption[] => {
  const belongKey = `interface_belong_${deviceModel}`;
  const group = (assocList || []).find((g) => g.model_asst_id === belongKey);
  if (!group?.inst_list) return [];
  return group.inst_list.map((i) => ({ id: String(i._id), name: i.inst_name }));
};

// 建 connect 关联的请求体
export const buildConnectPayload = (srcPortId: string, dstPortId: string) => ({
  model_asst_id: CONNECT_MODEL_ASST_ID,
  src_model_id: INTERFACE_MODEL,
  dst_model_id: INTERFACE_MODEL,
  asst_id: CONNECT_ASST_ID,
  src_inst_id: Number(srcPortId),
  dst_inst_id: Number(dstPortId),
});

// 建 belong 关联（端口 -> 设备）的请求体
export const buildBelongPayload = (
  portId: string,
  deviceId: string,
  deviceModel: string
) => ({
  model_asst_id: `interface_belong_${deviceModel}`,
  src_model_id: INTERFACE_MODEL,
  dst_model_id: deviceModel,
  asst_id: BELONG_ASST_ID,
  src_inst_id: Number(portId),
  dst_inst_id: Number(deviceId),
});

export interface ConnValidationCtx {
  sourceId: string;
  targetId: string;
  modelOf: (id: string) => string | undefined;
  networkModels: string[];
}

// 连线前校验：A!=B、两端都是网络设备
export const validateConnection = (
  ctx: ConnValidationCtx
): { ok: boolean; reason?: string } => {
  if (!ctx.sourceId || !ctx.targetId) return { ok: false, reason: 'empty' };
  if (ctx.sourceId === ctx.targetId) return { ok: false, reason: 'self' };
  const sm = ctx.modelOf(ctx.sourceId);
  const tm = ctx.modelOf(ctx.targetId);
  if (!sm || !tm) return { ok: false, reason: 'unknown' };
  if (
    !isNetworkModel(sm, ctx.networkModels) ||
    !isNetworkModel(tm, ctx.networkModels)
  ) {
    return { ok: false, reason: 'not_network' };
  }
  return { ok: true };
};

// 把确认后的连线构造成 NetworkTopoLink，供合并进图
export const buildLinkFromConnection = (args: {
  relationshipId: string;
  sourceDevice: string;
  targetDevice: string;
  sourcePortName: string;
  targetPortName: string;
}): NetworkTopoLink => ({
  relationship_id: String(args.relationshipId),
  source_device: args.sourceDevice,
  source_inst_name: args.sourcePortName,
  target_device: args.targetDevice,
  target_inst_name: args.targetPortName,
  asst_id: CONNECT_ASST_ID,
});

// 从某设备的网络拓扑链路里，取出该设备「已被连线占用」的端口名集合。
// 链路 source/target_inst_name 即接口 inst_name（后端 local_if=i.inst_name），与端口下拉的 name 一致。
export const extractOccupiedPortNames = (
  links: Array<{
    source_device?: string | number;
    source_inst_name?: string;
    target_device?: string | number;
    target_inst_name?: string;
  }>,
  deviceId: string
): Set<string> => {
  const set = new Set<string>();
  const dev = String(deviceId);
  (links || []).forEach((l) => {
    if (String(l.source_device) === dev && l.source_inst_name) {
      set.add(l.source_inst_name);
    }
    if (String(l.target_device) === dev && l.target_inst_name) {
      set.add(l.target_inst_name);
    }
  });
  return set;
};

// 从边 id（edge-<relId>）解析 relationship_id
export const relationshipIdFromEdgeId = (edgeId: string): string =>
  edgeId.startsWith('edge-') ? edgeId.slice('edge-'.length) : edgeId;

// 游离节点落点：在中心附近做螺旋偏移，避开已有坐标
export const nextFloatingPosition = (
  index: number,
  step = 320
): { x: number; y: number } => {
  const ring = Math.floor(index / 8) + 1;
  const angle = ((index % 8) / 8) * Math.PI * 2;
  return { x: Math.cos(angle) * step * ring, y: Math.sin(angle) * step * ring };
};
