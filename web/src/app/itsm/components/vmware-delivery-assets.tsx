'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Alert, Button } from 'antd';
import { DatabaseOutlined } from '@ant-design/icons';
import { useItsmApi, type VmwareDeliveryAsset } from '../api/useItsmApi';

export function VmwareDeliveryAssets({ ticketId }: { ticketId: number }) {
  const { getTicketVmwareAssets } = useItsmApi();
  const [busy, setBusy] = useState(false);
  const [items, setItems] = useState<VmwareDeliveryAsset[]>();
  const [failed, setFailed] = useState(false);
  const load = async () => {
    setBusy(true);
    setFailed(false);
    try {
      setItems((await getTicketVmwareAssets(ticketId)).items);
    } catch {
      setItems(undefined);
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };
  return <div className="mt-4 space-y-2">
    <Button icon={<DatabaseOutlined aria-hidden />} loading={busy} onClick={() => void load()}>查询 CMDB 资产</Button>
    {failed && <Alert type="error" showIcon message="资产查询失败，请检查访问权限或稍后重试" />}
    {items && <ul aria-label="虚拟机资产" className="space-y-1">{items.map(item => (
      <li key={item.delivery_id} className="flex gap-2">
        {item.url ? <Link href={item.url} className="text-[var(--color-primary)]">{item.hostname || item.delivery_id}</Link> : <>{item.hostname || item.delivery_id}<span>待关联</span></>}
      </li>
    ))}</ul>}
  </div>;
}
