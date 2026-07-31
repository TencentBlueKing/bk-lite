import { Tag } from 'antd';
import type { CatalogStatus } from '@/app/apm/types';

const statusCopy: Record<CatalogStatus, { color: string; label: string }> = {
  active: { color: 'success', label: '活跃' },
  silent: { color: 'warning', label: '静默' },
  archived: { color: 'default', label: '已归档' },
};

export default function ApmStatusTag({ status }: { status: CatalogStatus }) {
  const item = statusCopy[status];
  return <Tag color={item.color}>{item.label}</Tag>;
}
