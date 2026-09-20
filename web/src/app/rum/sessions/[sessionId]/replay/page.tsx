'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Empty, Segmented } from 'antd';

import { useRumQueries, type RumReplayManifest } from '@/app/rum/api';
import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import RumBackButton from '@/app/rum/components/rum-back-button';
import {
  RUM_WORKBENCH_ASIDE_WIDTH,
  RUM_WORKBENCH_HEAD,
} from '@/app/rum/components/rum-dual-workbench';
import { RumReplayPageSkeleton, RumReplayPlayerSkeleton } from '@/app/rum/components/rum-skeleton';
import { degradationReason } from '@/app/rum/lib/degradation';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { loadReplayRecording } from '@/app/rum/sessions/lib/replay-data';
import ReplayPlayer from '@/app/rum/sessions/ui/replay-player';
import { useAuth } from '@/context/auth';
import { useTranslation } from '@/utils/i18n';

export default function SessionReplayPage() {
  const { t } = useTranslation();
  const { token } = useAuth();
  const params = useParams<{ sessionId: string }>();
  const sessionId = decodeURIComponent(params.sessionId || '');
  const { application, searchParams } = useRumSearchParams();
  const app = application || searchParams.get('application') || '';
  const { getReplayManifest, createReplayGrant } = useRumQueries();

  const [manifest, setManifest] = useState<RumReplayManifest | null>(null);
  const [pending, setPending] = useState(true);
  const [activeRecording, setActiveRecording] = useState('');
  const [events, setEvents] = useState<unknown[]>([]);
  const [loadingRecording, setLoadingRecording] = useState(false);

  const back = `/rum/sessions/${encodeURIComponent(sessionId)}?application=${encodeURIComponent(app)}`;

  const loadManifest = useCallback(async () => {
    if (!app || !sessionId) {
      setPending(false);
      return;
    }
    setPending(true);
    try {
      setManifest(await getReplayManifest(app, sessionId));
    } catch {
      setManifest(null);
    } finally {
      setPending(false);
    }
  }, [app, getReplayManifest, sessionId]);

  useEffect(() => {
    void loadManifest();
  }, [loadManifest]);

  const recordings = manifest?.recordings || [];
  const degrade = degradationReason(manifest);

  useEffect(() => {
    if (!manifest || manifest.state !== 'ready' || recordings.length === 0) return;
    const recordingId = recordings[0].recordingId;
    setActiveRecording(recordingId);
    setLoadingRecording(true);
    void loadReplayRecording(manifest, app, sessionId, recordingId, createReplayGrant, token)
      .then((loaded) => {
        setEvents(loaded);
      })
      .catch(() => {
        setEvents([]);
      })
      .finally(() => setLoadingRecording(false));
    // only auto-load first recording when manifest changes
     
  }, [manifest, app, sessionId]);

  const selectRecording = async (recordingId: string) => {
    if (!manifest || recordingId === activeRecording) return;
    setActiveRecording(recordingId);
    setEvents([]);
    setLoadingRecording(true);
    try {
      setEvents(
        await loadReplayRecording(manifest, app, sessionId, recordingId, createReplayGrant, token),
      );
    } catch {
      setEvents([]);
    } finally {
      setLoadingRecording(false);
    }
  };

  const backControl = <RumBackButton href={back} />;

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{t('rum.sessions.replay', '会话回放')}</h1>

      {pending && !manifest ? (
        <RumReplayPageSkeleton />
      ) : (
        <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden rounded-lg bg-[var(--color-bg)]">
          <section className="flex min-h-0 min-w-0 flex-1 flex-col">
            <div className={`${RUM_WORKBENCH_HEAD} gap-3`}>{backControl}</div>
            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-3.5">
              {!manifest ? (
                <div className="flex min-h-0 flex-1 items-center justify-center">
                  <Empty description={t('rum.sessions.replayUnavailable', '无法加载回放清单')} />
                </div>
              ) : (
                <>
                  {degrade ? <PipelineDegradedBanner reason={degrade} /> : null}
                  <div className="shrink-0 text-sm text-[var(--color-text-3)]">
                    <span>
                      {t('rum.sessions.replayState', '状态')}:{' '}
                      <span className="font-medium text-[var(--color-text-1)]">{manifest.state}</span>
                    </span>
                    <span className="ml-3">
                      {app} · {sessionId}
                    </span>
                  </div>
                  {manifest.state !== 'ready' || recordings.length === 0 ? (
                    <div className="flex min-h-0 flex-1 items-center justify-center">
                      <Empty
                        description={
                          <div className="mx-auto max-w-md">
                            <p className="m-0 text-sm font-semibold">
                              {t('rum.sessions.replayEmpty', '暂无可用回放')}
                            </p>
                            <p className="mt-1 text-xs text-[var(--color-text-3)]">
                              {t('rum.sessions.replayEmptyHint', '会话未录制，或片段尚未就绪。')}
                            </p>
                          </div>
                        }
                      />
                    </div>
                  ) : loadingRecording ? (
                    <RumReplayPlayerSkeleton />
                  ) : events.length > 0 ? (
                    <div className="min-h-0 flex-1 overflow-hidden">
                      <ReplayPlayer key={activeRecording} events={events} />
                    </div>
                  ) : (
                    <div className="flex min-h-0 flex-1 items-center justify-center">
                      <Empty description={t('rum.sessions.replayUnavailable', '无法加载回放清单')} />
                    </div>
                  )}
                </>
              )}
            </div>
          </section>

          <aside
            className={`flex ${RUM_WORKBENCH_ASIDE_WIDTH} shrink-0 flex-col border-l border-[var(--color-fill-2)]`}
          >
            <div className={RUM_WORKBENCH_HEAD}>
              {t('rum.sessions.replayRecordings', '录制分段')}
            </div>
            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3.5">
              {!manifest || recordings.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('rum.sessions.replayEmpty', '暂无可用回放')}
                />
              ) : (
                <>
                  {recordings.length > 1 ? (
                    <Segmented
                      block
                      value={activeRecording}
                      onChange={(value) => void selectRecording(String(value))}
                      options={recordings.map((item) => ({
                        value: item.recordingId,
                        label: item.pageId || item.recordingId.slice(0, 8),
                      }))}
                    />
                  ) : null}
                  <ul className="space-y-2 text-xs text-[var(--color-text-3)]">
                    {recordings.map((item) => (
                      <li
                        key={item.recordingId}
                        className="rounded-md border border-[var(--color-border-2)] p-2"
                      >
                        <div className="font-medium text-[var(--color-text-1)]">
                          {item.pageId || item.recordingId}
                        </div>
                        <div>
                          {item.segments.length} segments ·{' '}
                          {item.segments.reduce((sum, seg) => sum + seg.eventCount, 0)} events
                        </div>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
