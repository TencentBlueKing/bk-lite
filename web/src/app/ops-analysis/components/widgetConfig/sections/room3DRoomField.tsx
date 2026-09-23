'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Form, Select, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useRoom3DApi } from '@/app/ops-analysis/api/room3D';
import type { Room3DRoomOption } from '@/app/ops-analysis/types/sceneWidget';

export const Room3DRoomField = ({
  open,
  enabled,
}: {
  open: boolean;
  enabled: boolean;
}) => {
  const { t } = useTranslation();
  const { getRooms } = useRoom3DApi();
  const getRoomsRef = useRef(getRooms);
  getRoomsRef.current = getRooms;
  const [rooms, setRooms] = useState<Room3DRoomOption[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !enabled) return;
    let cancelled = false;
    setLoading(true);
    getRoomsRef.current()
      .then((payload) => {
        if (cancelled) return;
        setRooms(Array.isArray(payload?.items) ? payload.items : []);
      })
      .catch(() => {
        if (!cancelled) setRooms([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, open]);

  return (
    <Form.Item
      label={t('dashboard.room3DDefaultRoom')}
      name={['room3D', 'serverRoomId']}
    >
      <Select
        allowClear
        showSearch
        optionFilterProp="label"
        loading={loading}
        options={rooms.map((item) => ({ value: item.id, label: item.name }))}
        placeholder={t('dashboard.room3DDefaultRoomPlaceholder')}
        notFoundContent={loading ? <Spin size="small" /> : undefined}
      />
    </Form.Item>
  );
};
