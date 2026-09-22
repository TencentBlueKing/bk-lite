'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import { Empty } from 'antd';

import { useRumQueries, type RumReplayManifest } from '@/app/rum/api';
import PipelineDegradedBanner from '@/app/rum/components/pipeline-degraded';
import RumBackButton from '@/app/rum/components/rum-back-button';
import {
  RUM_WORKBENCH_ASIDE_WIDTH,
  RUM_WORKBENCH_HEAD,
} from '@/app/rum/components/rum-dual-workbench';
import { RumReplayPageSkeleton, RumReplayPlayerSkeleton } from '@/app/rum/components/rum-skeleton';
import { degradationReason } from '@/app/rum/lib/degradation';
import { formatDurationMs } from '@/app/rum/lib/format';
import { useRumSearchParams } from '@/app/rum/lib/search-params';
import { useRumAuthedEffect } from '@/app/rum/lib/use-authed-effect';
import { loadReplayRecording } from '@/app/rum/sessions/lib/replay-data';
import {
  eventsPlayableMs,
  formatReplayClock,
  isSnapshotOnly,
  presentReplayRecording,
} from '@/app/rum/sessions/lib/replay-present';
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
  const { getReplayManifest, createReplayGrant, authReady } = useRumQueries();

  const [manifest, setManifest] = useState<RumReplayManifest | null>(null);
  const [pending, setPending] = useState(true);
  const [activeRecording, setActiveRecording] = useState('');
  const [events, setEvents] = useState<unknown[]>([]);
  const [loadingRecording, setLoadingRecording] = useState(false);

  const back = `/rum/sessions/${encodeURIComponent(sessionId)}?application=${encodeURIComponent(app)}`;

  useRumAuthedEffect(
    authReady,
    (isCancelled) => {
      if (!app || !sessionId) {
        setPending(false);
        return;
      }
      setPending(true);
      void getReplayManifest(app, sessionId)
        .then((next) => {
          if (!isCancelled()) setManifest(next);
        })
        .catch(() => {
          if (!isCancelled()) setManifest(null);
        })
        .finally(() => {
          if (!isCancelled()) setPending(false);
        });
    },
    [app, getReplayManifest, sessionId],
  );

  const recordings = manifest?.recordings || [];
  const degrade = degradationReason(manifest);
  const presentedRecordings = useMemo(
    () =>
      recordings.map((recording, index) => ({
        recording,
        present: presentReplayRecording(recording, index),
      })),
    [recordings],
  );
  const activePresented = presentedRecordings.find(
    (item) => item.recording.recordingId === activeRecording,
  )?.present;
  const loadedPlayableMs = eventsPlayableMs(events);
  const loadedSnapshotOnly = events.length > 0 && isSnapshotOnly(loadedPlayableMs);

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
  const playableLabel = loadedSnapshotOnly
    ? t('rum.sessions.replaySnapshotOnly', '仅快照')
    : formatDurationMs(loadedPlayableMs || activePresented?.playableMs || 0);

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
                  <div className="shrink-0 space-y-1 text-sm text-[var(--color-text-3)]">
                    <div className="flex flex-wrap items-center gap-2">
                      <span>
                        {t('rum.sessions.replayState', '状态')}:{' '}
                        <span className="font-medium text-[var(--color-text-1)]">{manifest.state}</span>
                      </span>
                      <span>
                        {t('rum.sessions.replayPlayable', '本段可播')}:{' '}
                        <span className="font-medium text-[var(--color-text-1)]">{playableLabel}</span>
                      </span>
                      <span className="text-[var(--color-text-4)]">
                        {app} · {sessionId}
                      </span>
                    </div>
                    <p className="m-0 text-xs text-[var(--color-text-4)]">
                      {t(
                        'rum.sessions.replayNotSessionFilm',
                        '多页会话会拆成多段录制；一次播放一段，不是整段会话电影。',
                      )}
                    </p>
                    {loadedSnapshotOnly ? (
                      <p className="m-0 text-xs text-[var(--color-warning)]">
                        {t(
                          'rum.sessions.replaySnapshotOnlyHint',
                          '这段几乎只有页面快照，没有可播放的操作时间轴。',
                        )}
                      </p>
                    ) : null}
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
            <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3.5">
              {!manifest || recordings.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('rum.sessions.replayEmpty', '暂无可用回放')}
                />
              ) : (
                <ul className="m-0 list-none space-y-2 p-0">
                  {presentedRecordings.map(({ recording, present }) => {
                    const active = recording.recordingId === activeRecording;
                    const playableMs =
                      active && events.length > 0 ? loadedPlayableMs : present.playableMs;
                    const snapshotOnly = isSnapshotOnly(playableMs);
                    return (
                      <li key={recording.recordingId}>
                        <button
                          type="button"
                          aria-current={active ? 'true' : undefined}
                          onClick={() => void selectRecording(recording.recordingId)}
                          className={[
                            'w-full rounded-md border p-2.5 text-left transition-colors',
                            active
                              ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg)] shadow-[inset_3px_0_0_var(--color-primary)]'
                              : 'border-[var(--color-border-2)] bg-transparent hover:border-[var(--color-border-3)] hover:bg-[var(--color-fill-1)]',
                          ].join(' ')}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-medium text-[var(--color-text-1)]">
                              {t('rum.sessions.replayRecordingOrdinal', '录制 {n}', {
                                n: present.ordinal,
                              })}
                            </span>
                            <span className="text-xs text-[var(--color-text-3)]">
                              {snapshotOnly
                                ? t('rum.sessions.replaySnapshotOnly', '仅快照')
                                : `${t('rum.sessions.replayPlayable', '本段可播')} ${formatDurationMs(playableMs)}`}
                            </span>
                          </div>
                          <div className="mt-1 text-xs text-[var(--color-text-3)]">
                            {t('rum.sessions.replayRecordingMeta', '{segments} 段 · {events} 事件', {
                              segments: present.segmentCount,
                              events: present.eventCount,
                            })}
                          </div>
                          <div className="mt-0.5 text-[11px] text-[var(--color-text-4)]">
                            {formatReplayClock(present.startedAt)}
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
