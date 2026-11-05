'use client';

import React, { useEffect, useState } from 'react';
import { Modal, Select } from 'antd';
import useApiClient from '@/utils/request';

interface NodeOption {
  value: string;
  label: string;
}

interface ReassignCollectorModalProps {
  open: boolean;
  title: string;
  placeholder: string;
  confirmText: string;
  cancelText: string;
  onCancel: () => void;
  onConfirm: (nodeId: string) => Promise<void>;
}

const ReassignCollectorModal = ({
  open,
  title,
  placeholder,
  confirmText,
  cancelText,
  onCancel,
  onConfirm
}: ReassignCollectorModalProps) => {
  const { post } = useApiClient();
  const [nodeId, setNodeId] = useState<string>();
  const [options, setOptions] = useState<NodeOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    setNodeId(undefined);
    let cancelled = false;
    setLoading(true);
    post('/node_mgmt/api/node/search/?page=1&page_size=100', {})
      .then((res: { items?: { id?: string; name?: string }[] }) => {
        if (cancelled) return;
        setOptions(
          (res?.items || [])
            .filter((item) => item?.id)
            .map((item) => ({
              value: String(item.id),
              label: item.name ? `${item.name} (${item.id})` : String(item.id)
            }))
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, post]);

  return (
    <Modal
      open={open}
      title={title}
      okText={confirmText}
      cancelText={cancelText}
      confirmLoading={confirming}
      okButtonProps={{ disabled: !nodeId }}
      onCancel={onCancel}
      onOk={async () => {
        if (!nodeId) return;
        setConfirming(true);
        try {
          await onConfirm(nodeId);
        } finally {
          setConfirming(false);
        }
      }}
    >
      <Select
        className="w-full"
        showSearch
        optionFilterProp="label"
        loading={loading}
        placeholder={placeholder}
        value={nodeId}
        options={options}
        onChange={setNodeId}
      />
    </Modal>
  );
};

export default ReassignCollectorModal;
