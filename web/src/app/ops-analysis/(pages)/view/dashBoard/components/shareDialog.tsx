'use client';

import React, { useEffect, useState } from 'react';
import { Button, InputNumber, Modal, Radio, Space, Typography, message } from 'antd';
import { useDashboardShareApi } from '@/app/ops-analysis/api/dashboardShare';
import type { DashboardShareLinkDto } from '@/app/ops-analysis/types/dashboardShare';

interface ShareDialogProps {
  dashboardId: string | number;
  open: boolean;
  onClose: () => void;
}

const ShareDialog: React.FC<ShareDialogProps> = ({ dashboardId, open, onClose }) => {
  const api = useDashboardShareApi();
  const [permanent, setPermanent] = useState(false);
  const [days, setDays] = useState(7);
  const [links, setLinks] = useState<DashboardShareLinkDto[]>([]);
  const [loading, setLoading] = useState(false);

  const reload = async () => setLinks(await api.listShares(dashboardId));

  useEffect(() => {
    if (open) void reload();
  }, [open, dashboardId]);

  const create = async () => {
    setLoading(true);
    try {
      const link = await api.createOrUpdateShare(dashboardId, {
        permanent,
        ...(permanent ? {} : { duration_seconds: days * 86400 }),
      });
      await navigator.clipboard.writeText(`${window.location.origin}${link.url}`);
      message.success('分享链接已复制');
      await reload();
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal title="分享仪表盘" open={open} onCancel={onClose} footer={null} destroyOnHidden>
      <Space direction="vertical" className="w-full">
        <Radio.Group value={permanent} onChange={(event) => setPermanent(event.target.value)}>
          <Radio value={false}>限时有效</Radio>
          <Radio value>永久有效</Radio>
        </Radio.Group>
        {!permanent && (
          <InputNumber min={1} max={90} value={days} onChange={(value) => setDays(value ?? 7)} addonAfter="天" />
        )}
        <Button type="primary" loading={loading} onClick={create}>创建并复制链接</Button>
        {links.map((link) => (
          <Space key={link.id} className="justify-between w-full">
            <Typography.Text>
              {link.permanent ? '永久有效' : `有效至 ${link.expires_at ?? '--'}`}
            </Typography.Text>
            {link.status === 'active' && (
              <Button danger type="link" onClick={async () => { await api.revokeShare(dashboardId, link.id); await reload(); }}>
                撤销
              </Button>
            )}
          </Space>
        ))}
      </Space>
    </Modal>
  );
};

export default ShareDialog;

