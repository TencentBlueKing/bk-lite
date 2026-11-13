'use client';

import { useEffect, useState } from 'react';
import { Button, Modal, Select, Spin, Tag, message } from 'antd';
import {
  CopyOutlined,
  DesktopOutlined,
  ExportOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import {
  SCREEN_DISPLAY_DURATIONS,
  useScreenDisplayApi,
  type ScreenDisplayGrantDto,
} from '@/app/ops-analysis/api/screenDisplay';

interface ScreenDisplayGrantModalProps {
  open: boolean;
  screenId?: string | number;
  onClose: () => void;
}

const formatExpiry = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

const ScreenDisplayGrantModal = ({
  open,
  screenId,
  onClose,
}: ScreenDisplayGrantModalProps) => {
  const { t } = useTranslation();
  const api = useScreenDisplayApi();
  const [grant, setGrant] = useState<ScreenDisplayGrantDto | null>(null);
  const [durationDays, setDurationDays] = useState<number>(30);
  const [loading, setLoading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [acting, setActing] = useState(false);

  useEffect(() => {
    if (!open || screenId == null) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadFailed(false);
    api.getGrant(screenId)
      .then((next) => {
        if (cancelled) return;
        setGrant(next);
        setDurationDays(next.duration_days || 30);
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api.getGrant, open, screenId, reloadKey]);

  const absoluteUrl = grant?.url ? `${window.location.origin}${grant.url}` : '';
  const expiresTime = grant?.expires_at ? formatExpiry(grant.expires_at) : '';
  const expiresLabel = expiresTime
    ? t('opsAnalysis.screen.displayExpiresAt', undefined, { time: expiresTime })
    : '';
  const durationOptions = SCREEN_DISPLAY_DURATIONS.map((days) => ({
    value: days,
    label: t('opsAnalysis.screen.displayDurationDays', undefined, { days }),
  }));

  const run = async (action: () => Promise<ScreenDisplayGrantDto>, success: string) => {
    setActing(true);
    try {
      const next = await action();
      setGrant(next);
      setDurationDays(next.duration_days || 30);
      message.success(success);
    } catch (error) {
      const payload = (error as { payload?: { data?: { reason?: string }; reason?: string; message?: string } }).payload;
      const reason = payload?.data?.reason || payload?.reason;
      if (reason === 'exists' && screenId != null) {
        try {
          const current = await api.getGrant(screenId);
          setGrant(current);
          setDurationDays(current.duration_days || 30);
          return;
        } catch {
          setLoadFailed(true);
        }
      }
      if (reason === 'expired') {
        message.warning(t('opsAnalysis.screen.displayResumeExpired'));
      } else {
        message.error(payload?.message || t('opsAnalysis.screen.displayActionFailed'));
      }
    } finally {
      setActing(false);
    }
  };

  const confirmRegenerate = () => {
    if (screenId == null) return;
    Modal.confirm({
      title: t('opsAnalysis.screen.displayRegenerateConfirmTitle'),
      content: t('opsAnalysis.screen.displayRegenerateConfirm'),
      centered: true,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: () => run(
        () => api.regenerateGrant(screenId, durationDays),
        t('opsAnalysis.screen.displayRegenerated'),
      ),
    });
  };

  const confirmPause = () => {
    if (screenId == null) return;
    Modal.confirm({
      title: t('opsAnalysis.screen.displayPauseConfirmTitle'),
      content: t('opsAnalysis.screen.displayPauseConfirm'),
      centered: true,
      okText: t('opsAnalysis.screen.displayPauseConfirmOk'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      onOk: () => run(
        () => api.pauseGrant(screenId),
        t('opsAnalysis.screen.displayPaused'),
      ),
    });
  };

  const copyLink = async () => {
    if (!absoluteUrl) return;
    try {
      await navigator.clipboard.writeText(absoluteUrl);
      message.success(t('opsAnalysis.screen.displayCopied'));
    } catch {
      message.error(t('opsAnalysis.screen.displayCopyFailed'));
    }
  };

  const configured = Boolean(grant?.configured);
  const state = grant?.state;
  const badgeColor = state === 'paused' ? 'warning' : state === 'expired' ? 'error' : 'success';
  const actionButtonClass = 'shrink-0 !h-8 !rounded-full !border-transparent !bg-[var(--color-text-1)] !px-4 !text-[var(--color-bg)] hover:!bg-[var(--color-text-1)] hover:!text-[var(--color-bg)]';
  const quietButtonClass = 'shrink-0 !h-8 !rounded-full !px-4';

  return (
    <Modal
      open={open}
      centered
      width={640}
      styles={{
        header: { borderBottom: 'none', paddingBottom: 0 },
        body: { maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' },
      }}
      title={(
        <div className="pr-6">
          <span className="flex items-center gap-2 text-base font-semibold leading-6 text-[var(--color-text-1)]">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-[color-mix(in_srgb,var(--color-primary)_45%,var(--color-border-1))] text-base text-[var(--color-primary)]">
              <DesktopOutlined />
            </span>
            {t('opsAnalysis.screen.displayModalTitle')}
          </span>
          <span className="mt-2 block text-xs font-normal leading-5 text-[var(--color-text-3)]">
            {t('opsAnalysis.screen.displayHint')}
          </span>
        </div>
      )}
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      {loading ? (
        <div className="flex justify-center py-10">
          <Spin />
        </div>
      ) : loadFailed || !grant ? (
        <div className="flex flex-col items-start gap-3 py-4">
          <p className="m-0 text-sm text-[var(--color-text-1)]">
            {t('opsAnalysis.screen.displayLoadFailed')}
          </p>
          <Button onClick={() => setReloadKey((key) => key + 1)}>
            {t('common.refresh')}
          </Button>
        </div>
      ) : (
        <div>
          <div className="pb-5 pt-4">
            <div className="text-sm font-semibold leading-5 text-[var(--color-text-1)]">
              {t('opsAnalysis.screen.displayDuration')}
            </div>
            <div className="mt-3 flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <Select
                  className="block h-8 w-full [&_.ant-select-selector]:!h-8"
                  value={durationDays}
                  options={durationOptions}
                  onChange={setDurationDays}
                  disabled={acting || loading}
                />
              </div>
              {configured ? (
                <Button
                  className={quietButtonClass}
                  icon={<ReloadOutlined aria-hidden />}
                  loading={acting}
                  onClick={confirmRegenerate}
                >
                  {t('opsAnalysis.screen.displayRegenerate')}
                </Button>
              ) : (
                <Button
                  type="primary"
                  className={actionButtonClass}
                  loading={acting}
                  disabled={screenId == null}
                  onClick={() => screenId != null && run(
                    () => api.createGrant(screenId, durationDays),
                    t('opsAnalysis.screen.displayCreated'),
                  )}
                >
                  {t('opsAnalysis.screen.displayCreate')}
                </Button>
              )}
            </div>
          </div>
          <div className="pb-1 pt-1">
            {configured ? (
              <>
                <div className="flex items-center justify-start gap-2">
                  <div className="text-sm font-semibold leading-5 text-[var(--color-text-1)]">
                    {t('opsAnalysis.screen.displayAccessLink')}
                  </div>
                  <Tag bordered={false} color={badgeColor} className="m-0">
                    {t(`opsAnalysis.screen.displayStatusBadge.${state}`)}
                  </Tag>
                </div>
                {expiresLabel ? (
                  <div className="mt-3 flex h-8 items-center rounded-md bg-[var(--color-fill-1)] px-3 text-left text-sm tabular-nums text-[var(--color-text-2)]">
                    {expiresLabel}
                  </div>
                ) : null}
                {state === 'active' && absoluteUrl ? (
                  <div className="mt-3 flex items-center gap-3">
                    <div className="flex h-8 min-w-0 flex-1 items-center gap-2 rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)] px-3">
                      <p className="m-0 min-w-0 flex-1 truncate whitespace-nowrap text-sm text-[var(--color-text-2)]" title={absoluteUrl}>
                        {absoluteUrl}
                      </p>
                      <ExportOutlined aria-hidden className="shrink-0 text-[var(--color-text-3)]" />
                    </div>
                    <Button
                      type="primary"
                      className={actionButtonClass}
                      icon={<CopyOutlined aria-hidden />}
                      onClick={copyLink}
                    >
                      {t('opsAnalysis.screen.displayCopy')}
                    </Button>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="m-0 text-xs leading-5 text-[var(--color-text-3)]">
                {t('opsAnalysis.screen.displayEmpty')}
              </p>
            )}
          </div>
          {state === 'active' ? (
            <div className="mt-4 flex justify-start border-t border-[var(--color-border-2)] pt-3">
              <Button
                type="link"
                danger
                className="h-auto px-0"
                loading={acting}
                onClick={confirmPause}
              >
                {t('opsAnalysis.screen.displayPause')}
              </Button>
            </div>
          ) : null}
          {state === 'paused' ? (
            <div className="flex justify-start pt-4">
              <Button
                type="link"
                className="h-auto px-0"
                loading={acting}
                onClick={() => screenId != null && run(
                  () => api.resumeGrant(screenId),
                  t('opsAnalysis.screen.displayResumed'),
                )}
              >
                {t('opsAnalysis.screen.displayResume')}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </Modal>
  );
};

export default ScreenDisplayGrantModal;
