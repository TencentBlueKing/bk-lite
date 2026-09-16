'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button, Spin } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import { useTranslation } from '@/utils/i18n';
import Room3D from '@/app/ops-analysis/components/widgets/room3D';
import { useRoom3DEmbedApi } from '@/app/ops-analysis/api/room3D';
import { publicWidgetErrorMessage } from './publicWidgetError';

export interface Room3DEmbedProps {
  instUuid: string;
}

const Room3DEmbed = ({ instUuid }: Room3DEmbedProps) => {
  const { t } = useTranslation();
  const { getRoom3DLayout } = useRoom3DEmbedApi();
  const getRoom3DLayoutRef = useRef(getRoom3DLayout);
  getRoom3DLayoutRef.current = getRoom3DLayout;
  const [rawData, setRawData] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const uuid = String(instUuid || '').trim();
    if (!uuid) {
      setLoading(false);
      setError(t('common.loadFailed'));
      setRawData(null);
      return;
    }
    setLoading(true);
    setError(null);
    setRawData(null);
    getRoom3DLayoutRef
      .current(uuid)
      .then((data) => {
        if (!cancelled) setRawData(data);
      })
      .catch((requestError) => {
        if (!cancelled) {
          setError(
            publicWidgetErrorMessage(
              requestError,
              t,
              'dashboard.room3DNoData',
            ),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [instUuid, reloadKey, t]);

  if (loading) {
    return (
      <div className="flex h-full min-h-[280px] items-center justify-center">
        <Spin />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex h-full min-h-[280px] flex-col items-center justify-center gap-3">
        <CompactEmptyState description={error} />
        <Button onClick={() => setReloadKey((current) => current + 1)}>
          {t('common.retry')}
        </Button>
      </div>
    );
  }

  return (
    <div className="h-full min-h-[280px] min-w-0">
      <Room3D rawData={rawData} />
    </div>
  );
};

export default Room3DEmbed;
