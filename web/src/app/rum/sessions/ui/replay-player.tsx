'use client';

import '@grafana/rrweb-replay/dist/style.css';

import type { eventWithTime, Replayer as RrwebReplayer } from '@grafana/rrweb';
import { useEffect, useRef, useState } from 'react';
import { Button, Segmented, Slider } from 'antd';
import { PauseCircleOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';

import { useTranslation } from '@/utils/i18n';

const REPLAY_DOCUMENT_CSP =
  "default-src 'none'; img-src data: blob:; media-src data: blob:; font-src data:; style-src 'unsafe-inline'";

function formatClock(value: number) {
  const seconds = Math.max(0, Math.floor(value / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

export default function ReplayPlayer({ events }: { events: unknown[] }) {
  const { t } = useTranslation();
  const rootRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<RrwebReplayer | null>(null);
  const frameRef = useRef(0);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeed] = useState(1);

  useEffect(() => {
    const root = rootRef.current;
    if (!root || events.length === 0) return;
    let disposed = false;
    const ownerDocument = root.ownerDocument;
    const originalCreateElement = ownerDocument.createElement;
    const meta = events.find(
      (event) => typeof event === 'object' && event !== null && 'type' in event && event.type === 4,
    ) as { data?: { width?: unknown; height?: unknown } } | undefined;
    const viewportWidth = typeof meta?.data?.width === 'number' ? meta.data.width : 1280;
    const viewportHeight = typeof meta?.data?.height === 'number' ? meta.data.height : 720;
    let resizeObserver: ResizeObserver | undefined;

    void import('@grafana/rrweb-replay').then(({ Replayer }) => {
      if (disposed) return;
      ownerDocument.createElement = ((name: string, options?: ElementCreationOptions) => {
        const element = originalCreateElement.call(ownerDocument, name, options);
        if (element instanceof HTMLIFrameElement) element.setAttribute('csp', REPLAY_DOCUMENT_CSP);
        return element;
      }) as typeof ownerDocument.createElement;
      try {
        const player = new Replayer(events as eventWithTime[], {
          root,
          speed,
          skipInactive: false,
          showWarning: false,
          triggerFocus: false,
        });
        player.iframe.setAttribute('csp', REPLAY_DOCUMENT_CSP);
        if (!root.contains(player.wrapper)) root.append(player.wrapper);
        const resize = () => {
          const scale = Math.min(1, root.clientWidth / Math.max(1, viewportWidth));
          player.wrapper.style.width = `${viewportWidth}px`;
          player.wrapper.style.height = `${viewportHeight}px`;
          player.wrapper.style.transform = `scale(${scale})`;
          player.wrapper.style.transformOrigin = 'top left';
          root.style.height = `${Math.ceil(viewportHeight * scale)}px`;
        };
        resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(root);
        resize();
        player.pause(0);
        playerRef.current = player;
        setDuration(player.getMetaData().totalTime);
      } finally {
        ownerDocument.createElement = originalCreateElement;
      }
    });

    return () => {
      disposed = true;
      cancelAnimationFrame(frameRef.current);
      resizeObserver?.disconnect();
      playerRef.current?.destroy();
      playerRef.current = null;
      root.replaceChildren();
    };
    // speed applied via setConfig below
     
  }, [events]);

  useEffect(() => {
    const tick = () => {
      const player = playerRef.current;
      if (!player) return;
      const current = player.getCurrentTime();
      setPosition(current);
      if (current >= duration) {
        setPlaying(false);
        return;
      }
      frameRef.current = requestAnimationFrame(tick);
    };
    cancelAnimationFrame(frameRef.current);
    if (playing) frameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameRef.current);
  }, [duration, playing]);

  const seek = (next: number) => {
    playerRef.current?.pause(next);
    setPosition(next);
    setPlaying(false);
  };

  const toggle = () => {
    const player = playerRef.current;
    if (!player) return;
    if (playing) {
      player.pause();
      setPlaying(false);
    } else {
      player.play(position >= duration ? 0 : position);
      setPlaying(true);
    }
  };

  const changeSpeed = (next: number) => {
    playerRef.current?.setConfig({ speed: next });
    setSpeed(next);
  };

  return (
    <div className="overflow-hidden rounded-md border border-[var(--color-border-2)] bg-black">
      <div
        ref={rootRef}
        className="min-h-80 overflow-hidden bg-white [&_.replayer-wrapper]:origin-top-left"
      />
      <div className="flex flex-wrap items-center gap-2 border-t border-white/10 bg-zinc-950 px-3 py-2 text-white">
        <Button
          type="text"
          className="text-white hover:bg-white/10 hover:text-white"
          icon={playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
          aria-label={
            playing
              ? t('rum.sessions.replayPause', '暂停回放')
              : t('rum.sessions.replayPlay', '播放回放')
          }
          onClick={toggle}
        />
        <Button
          type="text"
          className="text-white hover:bg-white/10 hover:text-white"
          icon={<ReloadOutlined />}
          aria-label={t('rum.sessions.replayRestart', '从头播放')}
          onClick={() => seek(0)}
        />
        <span className="w-24 text-center text-xs tabular-nums">
          {formatClock(position)} / {formatClock(duration)}
        </span>
        <Slider
          className="min-w-40 flex-1"
          min={0}
          max={Math.max(1, duration)}
          value={Math.min(position, duration)}
          onChange={(value) => seek(Number(value))}
          tooltip={{ formatter: (value) => formatClock(Number(value ?? 0)) }}
          aria-label="Replay progress"
        />
        <Segmented
          size="small"
          value={speed}
          onChange={(value) => changeSpeed(Number(value))}
          options={[1, 2, 4].map((value) => ({ value, label: `${value}×` }))}
        />
      </div>
    </div>
  );
}
