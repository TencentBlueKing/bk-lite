import {
  buildStorageInstanceId,
  parsePythonTupleString
} from '@/app/monitor/dashboards/shared/utils/instance';

/** 存储键、单元素 tuple 和标量 instance_id 互相认作同一实例。 */
export const sameMonitorInstance = (left: unknown, right: unknown) => {
  const a = String(left ?? '').trim();
  const b = String(right ?? '').trim();
  if (!a || !b) return false;
  if (a === b) return true;
  const aTuple = parsePythonTupleString(a);
  const bTuple = parsePythonTupleString(b);
  const aStorage = aTuple?.length ? buildStorageInstanceId(aTuple) : a;
  const bStorage = bTuple?.length ? buildStorageInstanceId(bTuple) : b;
  if (aStorage === bStorage) return true;
  if (aTuple?.length === 1 && aTuple[0] === b) return true;
  if (bTuple?.length === 1 && bTuple[0] === a) return true;
  return false;
};

/** 用实例名缩小资产列表。没有可读名字时用身份第一段。 */
export const instanceConfigSearchKeyword = (instanceId: string, instanceName: string) => {
  const name = instanceName.trim();
  if (name && name !== '--') return name;
  const tuple = parsePythonTupleString(instanceId.trim());
  if (tuple?.[0]) return tuple[0];
  return instanceId.trim();
};
