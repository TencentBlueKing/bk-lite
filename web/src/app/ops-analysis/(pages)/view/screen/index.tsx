'use client';

import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useState,
} from 'react';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useScreenApi } from '@/app/ops-analysis/api/screen';
import type {
  ScreenProps,
  ScreenViewSets,
  ScreenViewportConfig,
} from '@/app/ops-analysis/types/screen';
import {
  AppViewFullscreenExit,
  useAppViewFullscreen,
} from '@/app/ops-analysis/components/appFullscreen';
import CanvasWorkspace from '../components/canvasWorkspace';
import ScreenCanvas from './components/screenCanvas';
import ScreenConfigModal from './components/screenConfigModal';
import ScreenToolbar from './components/screenToolbar';
import {
  buildDefaultScreenViewSets,
  normalizeScreenViewSets,
  updateScreenViewport,
} from './utils/viewport';

export interface ScreenRef {
  hasUnsavedChanges: () => boolean;
}

const Screen = forwardRef<ScreenRef, ScreenProps>(({ selectedScreen }, ref) => {
  const { t } = useTranslation();
  const { getScreenDetail, saveScreen } = useScreenApi();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [viewSets, setViewSets] = useState<ScreenViewSets>(
    buildDefaultScreenViewSets,
  );
  const [savedViewSets, setSavedViewSets] = useState<ScreenViewSets>(
    buildDefaultScreenViewSets,
  );
  const { isFullscreen, enterFullscreen, exitFullscreen } =
    useAppViewFullscreen();

  const hasUnsavedChanges = useCallback(
    () => JSON.stringify(viewSets) !== JSON.stringify(savedViewSets),
    [savedViewSets, viewSets],
  );

  useImperativeHandle(ref, () => ({
    hasUnsavedChanges,
  }));

  useEffect(() => {
    const screenId = selectedScreen?.data_id;
    if (!screenId) {
      const emptyViewSets = buildDefaultScreenViewSets();
      setViewSets(emptyViewSets);
      setSavedViewSets(emptyViewSets);
      return;
    }

    let cancelled = false;
    setLoading(true);
    getScreenDetail(screenId)
      .then((data) => {
        if (cancelled) return;

        const normalized = normalizeScreenViewSets(data?.view_sets);
        setViewSets(normalized);
        setSavedViewSets(normalized);
      })
      .catch((error) => {
        console.error('Failed to load screen:', error);
        if (!cancelled) {
          const fallback = buildDefaultScreenViewSets();
          setViewSets(fallback);
          setSavedViewSets(fallback);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [getScreenDetail, selectedScreen?.data_id]);

  const handleSaveViewport = async (viewport: ScreenViewportConfig) => {
    if (!selectedScreen?.data_id) return;

    const nextViewSets = updateScreenViewport(viewSets, viewport);
    setSaving(true);
    try {
      await saveScreen(selectedScreen.data_id, {
        name: selectedScreen.name,
        desc: selectedScreen.desc,
        groups: selectedScreen.groups,
        view_sets: nextViewSets,
      });
      setViewSets(nextViewSets);
      setSavedViewSets(nextViewSets);
      setSettingsOpen(false);
      message.success(t('opsAnalysis.screen.saveSuccess'));
    } catch (error) {
      console.error('Failed to save screen viewport:', error);
      message.error(t('opsAnalysis.screen.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  if (isFullscreen) {
    return (
      <div className="fixed inset-0 z-[1000] bg-slate-950">
        <AppViewFullscreenExit visible onExit={exitFullscreen} />
        <ScreenCanvas viewSets={viewSets} fullscreen />
      </div>
    );
  }

  return (
    <>
      <CanvasWorkspace
        selectedItem={selectedScreen}
        loading={loading}
        titleFallback={t('opsAnalysis.screen.title')}
        emptyDescription={t('opsAnalysis.screen.selectFirst')}
        description={t('opsAnalysis.screen.basicShellDesc')}
        toolbar={
          <ScreenToolbar
            saving={saving}
            onOpenSettings={() => setSettingsOpen(true)}
            onPreview={enterFullscreen}
          />
        }
      >
        <ScreenCanvas viewSets={viewSets} />
      </CanvasWorkspace>
      <ScreenConfigModal
        open={settingsOpen}
        viewport={viewSets.viewport}
        saving={saving}
        onCancel={() => setSettingsOpen(false)}
        onSave={handleSaveViewport}
      />
    </>
  );
});

Screen.displayName = 'Screen';

export default Screen;
