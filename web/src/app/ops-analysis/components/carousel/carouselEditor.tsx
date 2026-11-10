'use client';

import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  Alert,
  Button,
  ConfigProvider,
  InputNumber,
  Modal,
  Popover,
  Spin,
  Tag,
  Tooltip,
  message,
  notification,
} from 'antd';
import {
  CaretRightOutlined,
  EditOutlined,
  FullscreenOutlined,
  HolderOutlined,
  LeftOutlined,
  PauseOutlined,
  PlusOutlined,
  RightOutlined,
} from '@ant-design/icons';
import OperateFormDrawer from '@/components/operate-form-drawer';
import CompactEmptyState from '@/components/compact-empty-state';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import { useTranslation } from '@/utils/i18n';
import { useUserInfoContext } from '@/context/userInfo';
import { useDirectoryApi } from '@/app/ops-analysis/api';
import { useCarouselApi } from '@/app/ops-analysis/api/carousel';
import type { CarouselItem } from '@/app/ops-analysis/types/carousel';
import type { DirItem } from '@/app/ops-analysis/types';
import { PlaybackSlideFrame, type PlaybackSlide } from './playbackCanvas';
import CarouselFullscreenChrome from './carouselFullscreenChrome';
import {
  reducePlaybackFrameError,
  resolvePlaybackStage,
  type HeldPlaybackFrame,
} from './playbackStage';
import { useCarouselPlaybackSession } from './useCarouselPlaybackSession';
import { readCachedCanvasDetail } from '@/app/ops-analysis/utils/canvasDetailCache';
import {
  CAROUSEL_DEFAULT_DWELL_SECONDS,
  CAROUSEL_DWELL_MAX_SECONDS,
  CAROUSEL_DWELL_MIN_SECONDS,
  CAROUSEL_MAX_ITEMS,
  carouselHiddenGroupIds,
  clampCarouselDwellSeconds,
  isCarouselHotkeyBlocked,
  isCarouselOverlayOpen,
} from '@/app/ops-analysis/utils/carouselPlayer';
import {
  canvasIdentityKey,
  carouselDurationMessage,
  carouselRoundSeconds,
  displayedMoveTarget,
  duplicateCanvasKeys,
  sameCarouselDraft,
  syncCarouselSelection,
  type CarouselDraftComparable,
} from '@/app/ops-analysis/utils/carouselDraft';
import {
  canStartCarouselPreview,
  manualPreviewStep,
  relocatePreviewIndexByKeys,
  shouldAutoOpenCarouselEditor,
  type CarouselEditorOpenRequest,
} from '@/app/ops-analysis/utils/carouselPreview';
import useBtnPermissions from '@/hooks/usePermissions';
import { fullscreenPopupContainer } from '@/utils/fullscreenPopupContainer';
import {
  CAROUSEL_FULLSCREEN_CONTROLS_IDLE_MS,
  planFullscreenChrome,
  type FullscreenChromeEvent,
} from '@/app/ops-analysis/utils/carouselFullscreenChrome';
import { CanvasTypeIcon } from './canvasTypeIcon';
import CanvasPicker, { type PickedCanvas } from './canvasPicker';

export interface CarouselEditorRef {
  hasUnsavedChanges: () => boolean;
  discardChanges: () => void;
}

interface DraftItem {
  key: string;
  id?: number;
  resource_type: CarouselItem['resource_type'];
  canvas_id: number;
  dwell_seconds: number | null;
  canvas_name: string;
  exists: boolean;
  visible: boolean;
  canvas_group_ids: number[];
}

interface CarouselEditorProps {
  carouselId: string | null;
  openEditorRequest?: CarouselEditorOpenRequest | null;
  infoRevision?: number;
  onSaved: (id: number) => void;
}

interface EditorFields {
  name: string;
  desc: string;
  groups: number[];
  defaultDwell: number | null;
}

const fieldsFromDetail = (detail: {
  name?: string;
  desc?: string;
  groups?: number[];
  default_dwell_seconds?: number | null;
}): EditorFields => ({
  name: detail.name ?? '',
  desc: detail.desc ?? '',
  groups: (detail.groups || []).map((groupId) => Number(groupId)),
  defaultDwell: detail.default_dwell_seconds ?? null,
});

const toComparable = (fields: EditorFields, rows: DraftItem[]): CarouselDraftComparable => ({
  name: fields.name,
  desc: fields.desc,
  groups: fields.groups,
  defaultDwell: fields.defaultDwell,
  items: rows.map((item) => ({
    resourceType: item.resource_type,
    canvasId: item.canvas_id,
    dwellSeconds: item.dwell_seconds,
  })),
});

const toDraft = (item: CarouselItem): DraftItem => ({
  key: `item-${item.id}`,
  id: item.id,
  resource_type: item.resource_type,
  canvas_id: item.canvas_id,
  dwell_seconds: item.dwell_seconds,
  canvas_name: item.canvas_name || '',
  exists: item.exists,
  visible: item.visible,
  canvas_group_ids: item.canvas_group_ids || [],
});

const moveItem = (items: DraftItem[], key: string, to: number): DraftItem[] => {
  const from = items.findIndex((item) => item.key === key);
  if (from < 0 || from === to) return items;
  const next = items.slice();
  const [row] = next.splice(from, 1);
  next.splice(Math.max(0, Math.min(to, next.length)), 0, row);
  return next;
};

const ItemRow = ({
  item,
  index,
  selected,
  canEdit,
  defaultDwell,
  hiddenLabels,
  canMoveUp,
  canMoveDown,
  canMoveTop,
  canMoveBottom,
  onActivate,
  onDwell,
  onMoveUp,
  onMoveDown,
  onMoveTop,
  onMoveBottom,
  onRemove,
}: {
  item: DraftItem;
  index: number;
  selected: boolean;
  canEdit: boolean;
  defaultDwell: number;
  hiddenLabels: string[];
  canMoveUp: boolean;
  canMoveDown: boolean;
  canMoveTop: boolean;
  canMoveBottom: boolean;
  onActivate: () => void;
  onDwell: (value: number | null) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onMoveTop: () => void;
  onMoveBottom: () => void;
  onRemove: () => void;
}) => {
  const { t } = useTranslation();
  const sortable = useSortable({ id: item.key, disabled: !canEdit });
  const invalid = !item.exists || !item.visible;
  const name = !item.exists
    ? (item.canvas_name || t('opsCarousel.deletedCanvas'))
    : !item.visible
      ? (item.canvas_name || t('opsCarousel.invisibleCanvas'))
      : (item.canvas_name || t('opsCarousel.unnamed'));
  return (
    <div
      ref={sortable.setNodeRef}
      style={{ transform: CSS.Transform.toString(sortable.transform), transition: sortable.transition }}
      className={`flex items-center gap-2 border-b border-[var(--color-border-1)] px-2 py-1.5 ${
        selected ? 'bg-[var(--color-fill-2)]' : ''
      }`}
      onClick={onActivate}
    >
      {canEdit && (
        <button
          type="button"
          className="w-6 cursor-grab text-[var(--color-text-3)]"
          aria-label={t('opsCarousel.drag')}
          onClick={(event) => event.stopPropagation()}
          {...sortable.attributes}
          {...sortable.listeners}
        >
          <HolderOutlined />
        </button>
      )}
      <span className="w-8 text-center text-xs text-[var(--color-text-3)]">{index + 1}</span>
      <CanvasTypeIcon type={item.resource_type} />
      <div className="min-w-0 flex-1">
        <div className={`truncate text-sm ${invalid ? 'text-[var(--color-text-3)]' : 'text-[var(--color-text-1)]'}`}>
          {name}
        </div>
      </div>
      {!item.exists && <Tag>{t('opsCarousel.invalidDeleted')}</Tag>}
      {item.exists && !item.visible && <Tag>{t('opsCarousel.invalidHidden')}</Tag>}
      {hiddenLabels.length > 0 && (
        <Popover
          content={(
            <div className="flex max-w-xs flex-col gap-1 text-sm">
              {hiddenLabels.map((label) => <span key={label}>{label}</span>)}
            </div>
          )}
        >
          <Tag onClick={(event) => event.stopPropagation()}>
            {t('opsCarousel.hiddenOrgCount', undefined, { count: hiddenLabels.length })}
          </Tag>
        </Popover>
      )}
      <div onClick={(event) => event.stopPropagation()}>
        {canEdit ? (
          <InputNumber
            min={CAROUSEL_DWELL_MIN_SECONDS}
            max={CAROUSEL_DWELL_MAX_SECONDS}
            value={item.dwell_seconds ?? undefined}
            placeholder={String(defaultDwell)}
            className="w-32"
            addonAfter={t('opsCarousel.seconds')}
            title={t('opsCarousel.dwellEmptyHint', undefined, { seconds: defaultDwell })}
            onChange={(value) => onDwell(value == null ? null : clampCarouselDwellSeconds(value))}
          />
        ) : (
          <span className="w-32 text-sm text-[var(--color-text-2)]">
            {item.dwell_seconds ?? defaultDwell} {t('opsCarousel.seconds')}
          </span>
        )}
      </div>
      {canEdit && (
        <div onClick={(event) => event.stopPropagation()}>
          <MoreActionsDropdown
            stopPropagation
            labelAlign="start"
            items={[
              { key: 'up', label: t('opsCarousel.moveUp'), disabled: !canMoveUp, onClick: onMoveUp },
              { key: 'down', label: t('opsCarousel.moveDown'), disabled: !canMoveDown, onClick: onMoveDown },
              { key: 'top', label: t('opsCarousel.moveTop'), disabled: !canMoveTop, onClick: onMoveTop },
              { key: 'bottom', label: t('opsCarousel.moveBottom'), disabled: !canMoveBottom, onClick: onMoveBottom },
              { key: 'remove', label: t('opsCarousel.remove'), danger: true, onClick: onRemove },
            ]}
          />
        </div>
      )}
    </div>
  );
};

const CarouselEditor = forwardRef<CarouselEditorRef, CarouselEditorProps>(({
  carouselId,
  openEditorRequest = null,
  infoRevision = 0,
  onSaved,
}, ref) => {
  const { t } = useTranslation();
  const { hasPermission } = useBtnPermissions();
  const { flatGroups } = useUserInfoContext();
  const { getCarousel, updateCarousel, prefetchCanvasDetail } = useCarouselApi();
  const { getDirectoryTree } = useDirectoryApi();
  const [items, setItems] = useState<DraftItem[]>([]);
  const [savedRows, setSavedRows] = useState<DraftItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fields, setFields] = useState<EditorFields>({
    name: '',
    desc: '',
    groups: [],
    defaultDwell: CAROUSEL_DEFAULT_DWELL_SECONDS,
  });
  const [savedDraft, setSavedDraft] = useState<CarouselDraftComparable | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [treeLoadFailed, setTreeLoadFailed] = useState(false);
  const [problemsOnly, setProblemsOnly] = useState(false);
  const [directories, setDirectories] = useState<DirItem[]>([]);
  const editorOpenRef = useRef(false);
  const appliedSignal = useRef(0);
  const loadedId = useRef<string | null>(null);
  const dragging = useRef(false);
  const seenToken = useRef<string | null>(null);
  const previousKeysRef = useRef<string[]>([]);
  const lockedIndexRef = useRef(0);
  const stageRef = useRef<HTMLDivElement>(null);
  const idleTimer = useRef<number | null>(null);
  const pausedRef = useRef(false);
  const hotzoneHoverRef = useRef(false);
  const applyChromePlanRef = useRef<(event: FullscreenChromeEvent) => void>(() => undefined);
  const [stageFullscreen, setStageFullscreen] = useState(false);
  const [controlsVisible, setControlsVisible] = useState(false);
  editorOpenRef.current = editorOpen;
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));
  const canEdit = hasPermission(['EditChart']);
  const canPlay = hasPermission(['View']);
  const defaultDwell = clampCarouselDwellSeconds(fields.defaultDwell, CAROUSEL_DEFAULT_DWELL_SECONDS);
  const dirty = savedDraft != null && !sameCarouselDraft(savedDraft, toComparable(fields, items));
  const draftDirtyRef = useRef(false);
  draftDirtyRef.current = editorOpen && dirty;
  const playbackAllowed = canStartCarouselPreview(editorOpen);

  const slides = useMemo<PlaybackSlide[]>(() => items.map((item) => ({
    key: item.key,
    resourceType: item.resource_type,
    canvasId: item.canvas_id,
    name: item.exists && item.visible ? (item.canvas_name || '') : '',
    dwellSeconds: clampCarouselDwellSeconds(item.dwell_seconds ?? defaultDwell),
    available: item.exists && item.visible,
  })), [defaultDwell, items]);
  const loadCanvas = useCallback((slide: PlaybackSlide, signal: AbortSignal) => (
    prefetchCanvasDetail(slide.resourceType, slide.canvasId, signal)
  ), [prefetchCanvasDetail]);
  const session = useCarouselPlaybackSession({
    slides,
    enabled: Boolean(carouselId) && !loading && slides.length > 0,
    loadDetail: loadCanvas,
    resetKey: carouselId || '',
    startPaused: true,
    confirmWhilePaused: true,
    retainUnavailable: true,
  });
  const player = session.player;
  const playbackSlideKeyRef = useRef('');
  const heldPlaybackRef = useRef<HeldPlaybackFrame | null>(null);
  const [heldPlaybackRevision, setHeldPlaybackRevision] = useState(0);
  const stageHoldingRef = useRef(false);
  const onPlaybackFrameError = useCallback(() => {
    const decision = reducePlaybackFrameError(
      stageHoldingRef.current,
      playbackSlideKeyRef.current,
    );
    if (!decision) return;
    if (decision.type === 'release-hold') {
      heldPlaybackRef.current = null;
      setHeldPlaybackRevision((revision) => revision + 1);
      return;
    }
    session.dispatch({ type: 'markUnavailable', key: decision.key });
  }, [session.dispatch]);
  const keysToken = items.map((item) => item.key).join('\u0000');

  const restoreSavedRef = useRef<() => void>(() => undefined);
  useImperativeHandle(ref, () => ({
    hasUnsavedChanges: () => draftDirtyRef.current,
    discardChanges: () => {
      draftDirtyRef.current = false;
      restoreSavedRef.current();
    },
  }), []);

  useEffect(() => {
    const nextKeys = keysToken ? keysToken.split('\u0000') : [];
    if (seenToken.current !== keysToken) {
      const nextIndex = relocatePreviewIndexByKeys(
        previousKeysRef.current,
        lockedIndexRef.current,
        nextKeys,
      );
      previousKeysRef.current = nextKeys;
      lockedIndexRef.current = Math.max(nextIndex, 0);
      seenToken.current = keysToken;
      if (nextIndex >= 0 && player.index !== nextIndex) {
        session.dispatch({ type: 'selectIndex', index: nextIndex });
      }
      return;
    }
    if (player.index >= 0) {
      lockedIndexRef.current = player.index;
    }
  }, [keysToken, player.index, player.visit, session.dispatch]);

  useEffect(() => {
    session.dispatch({ type: 'setPaused', paused: true });
    if (draftDirtyRef.current) return;
    setEditorOpen(false);
    setProblemsOnly(false);
  }, [carouselId, session.dispatch]);

  useEffect(() => {
    if (!(editorOpen && dirty)) return undefined;
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [dirty, editorOpen]);

  pausedRef.current = player.paused;
  applyChromePlanRef.current = (event) => {
    const plan = planFullscreenChrome(event, {
      paused: pausedRef.current,
      hoveringHotzone: hotzoneHoverRef.current,
    });
    setControlsVisible(plan.visible);
    if (idleTimer.current != null) window.clearTimeout(idleTimer.current);
    idleTimer.current = plan.armIdleTimer
      ? window.setTimeout(() => applyChromePlanRef.current('hide-elapsed'), CAROUSEL_FULLSCREEN_CONTROLS_IDLE_MS)
      : null;
  };

  useEffect(() => {
    const onChange = () => {
      const active = document.fullscreenElement === stageRef.current;
      setStageFullscreen(active);
      session.dispatch({ type: 'setPaused', paused: !active });
      if (active) return;
      hotzoneHoverRef.current = false;
      if (idleTimer.current != null) window.clearTimeout(idleTimer.current);
      idleTimer.current = null;
      setControlsVisible(false);
    };
    document.addEventListener('fullscreenchange', onChange);
    return () => {
      document.removeEventListener('fullscreenchange', onChange);
      if (idleTimer.current != null) window.clearTimeout(idleTimer.current);
    };
  }, [session.dispatch]);

  useEffect(() => {
    if (!stageFullscreen) return;
    applyChromePlanRef.current(player.paused ? 'paused' : 'resumed');
  }, [player.paused, stageFullscreen]);

  useEffect(() => {
    if (!stageFullscreen) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (isCarouselHotkeyBlocked(event.target) || isCarouselOverlayOpen()) return;
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft' || event.key === ' ') {
        event.preventDefault();
        session.dispatch({
          type: event.key === 'ArrowLeft' ? 'prev' : event.key === 'ArrowRight' ? 'next' : 'togglePause',
        });
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [session.dispatch, stageFullscreen]);

  useEffect(() => {
    if (!stageFullscreen) return undefined;
    message.config({ getContainer: fullscreenPopupContainer });
    notification.config({ getContainer: fullscreenPopupContainer });
    return () => {
      const restore = () => document.body;
      message.config({ getContainer: restore });
      notification.config({ getContainer: restore });
    };
  }, [stageFullscreen]);

  const groupName = useMemo(() => {
    const names = new Map<string, string>();
    (flatGroups || []).forEach((group) => {
      names.set(String(group.id), group.name);
    });
    return (groupId: number) => names.get(String(groupId)) || String(groupId);
  }, [flatGroups]);

  const applyDetail = useCallback((detail: {
    name: string;
    desc: string;
    groups: number[];
    default_dwell_seconds: number;
    items: CarouselItem[];
  }, identityOnly: boolean) => {
    const nextFields = fieldsFromDetail(detail);
    if (identityOnly) {
      setFields((current) => ({
        ...current,
        name: nextFields.name,
        desc: nextFields.desc,
        groups: nextFields.groups,
      }));
      setSavedDraft((current) => (
        current
          ? { ...current, name: nextFields.name, desc: nextFields.desc, groups: nextFields.groups }
          : current
      ));
      return;
    }
    const drafts = detail.items.map(toDraft);
    setFields(nextFields);
    setSavedRows(drafts);
    setItems(drafts);
    setSavedDraft(toComparable(nextFields, drafts));
  }, []);

  useEffect(() => {
    if (!carouselId) return undefined;
    if (draftDirtyRef.current && loadedId.current && loadedId.current !== carouselId) {
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    void getCarousel(carouselId).then((detail) => {
      if (cancelled || !carouselId) return;
      const identityOnly = editorOpenRef.current && loadedId.current === carouselId;
      applyDetail(detail, identityOnly);
      loadedId.current = carouselId;
      if (!identityOnly && duplicateCanvasKeys(detail.items.map((item) => ({
        resourceType: item.resource_type,
        canvasId: item.canvas_id,
      }))).length > 0) {
        message.warning(t('opsCarousel.duplicateHint'));
      }
    }).catch((error) => {
      console.error('Failed to load carousel:', error);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [applyDetail, carouselId, getCarousel, infoRevision, t]);

  useEffect(() => {
    if (!openEditorRequest || openEditorRequest.nonce === appliedSignal.current) return;
    if (loading || loadedId.current !== openEditorRequest.id) return;
    const open = shouldAutoOpenCarouselEditor({
      request: openEditorRequest,
      appliedNonce: appliedSignal.current,
      loadedId: loadedId.current,
      loading,
      itemCount: items.length,
      canEdit,
    });
    appliedSignal.current = openEditorRequest.nonce;
    if (!open) return;
    session.dispatch({ type: 'setPaused', paused: true });
    setEditorOpen(true);
  }, [canEdit, items.length, loading, openEditorRequest, session.dispatch]);

  const openEditor = () => {
    if (document.fullscreenElement === stageRef.current) {
      void document.exitFullscreen();
    }
    session.dispatch({ type: 'setPaused', paused: true });
    setEditorOpen(true);
  };

  const restoreSaved = () => {
    if (!savedDraft) {
      setEditorOpen(false);
      return;
    }
    setFields({
      name: savedDraft.name,
      desc: savedDraft.desc,
      groups: savedDraft.groups,
      defaultDwell: savedDraft.defaultDwell,
    });
    setItems(savedRows);
    setEditorOpen(false);
    setProblemsOnly(false);
  };
  restoreSavedRef.current = restoreSaved;

  const requestClose = () => {
    if (!dirty) {
      setEditorOpen(false);
      setProblemsOnly(false);
      return;
    }
    Modal.confirm({
      title: t('opsAnalysisSidebar.unsavedChanges'),
      content: t('opsAnalysisSidebar.unsavedChangesWarning'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      centered: true,
      onOk: restoreSaved,
    });
  };

  const openPicker = async () => {
    try {
      setDirectories(await getDirectoryTree());
      setTreeLoadFailed(false);
    } catch (error) {
      console.error('Failed to load canvases:', error);
      setDirectories([]);
      setTreeLoadFailed(true);
    }
    setPickerOpen(true);
  };

  const applyPicked = (picked: PickedCanvas[], treeKeys: string[]) => {
    if (treeLoadFailed) {
      setPickerOpen(false);
      return;
    }
    const stamp = Date.now();
    let sequence = 0;
    setItems((current) => syncCarouselSelection(
      current,
      picked,
      treeKeys,
      (item) => canvasIdentityKey(item.resource_type, item.canvas_id),
      (canvas) => ({
        key: `new-${canvas.resourceType}-${canvas.canvasId}-${stamp}-${sequence += 1}`,
        resource_type: canvas.resourceType,
        canvas_id: canvas.canvasId,
        dwell_seconds: null,
        canvas_name: canvas.name,
        exists: true,
        visible: true,
        canvas_group_ids: canvas.groups,
      }),
    ).items);
    setPickerOpen(false);
  };

  const persist = async () => {
    const duplicates = duplicateCanvasKeys(items.map((item) => ({
      resourceType: item.resource_type,
      canvasId: item.canvas_id,
    })));
    if (duplicates.length > 0) {
      Modal.warning({ title: t('opsCarousel.duplicateHint'), centered: true });
      return;
    }
    if (!carouselId) return;
    const payload = {
      name: fields.name.trim(),
      desc: fields.desc || '',
      groups: fields.groups,
      default_dwell_seconds: clampCarouselDwellSeconds(fields.defaultDwell),
      items: items.map((item) => ({
        ...(item.id ? { id: item.id } : {}),
        resource_type: item.resource_type,
        canvas_id: item.canvas_id,
        dwell_seconds: item.dwell_seconds,
      })),
    };
    setSaving(true);
    try {
      const saved = await updateCarousel(carouselId, payload);
      const drafts = saved.items.map(toDraft);
      const nextFields = fieldsFromDetail(saved);
      setFields(nextFields);
      setSavedRows(drafts);
      setItems(drafts);
      setSavedDraft(toComparable(nextFields, drafts));
      setEditorOpen(false);
      setProblemsOnly(false);
      session.dispatch({ type: 'setPaused', paused: true });
      onSaved(saved.id);
    } catch (error) {
      console.error('Failed to save carousel:', error);
    } finally {
      setSaving(false);
    }
  };

  const chooseIndex = (index: number) => {
    if (dragging.current) return;
    const row = items[index];
    if (!row) return;
    if (!playbackAllowed || !row.exists || !row.visible) {
      session.dispatch({ type: 'setPaused', paused: true });
    }
    lockedIndexRef.current = index;
    session.dispatch({ type: 'selectIndex', index });
  };

  const togglePlay = () => {
    if (!playbackAllowed) return;
    if (player.paused) {
      const current = slides[player.index];
      if (current && !current.available) {
        session.dispatch({ type: 'next' });
      }
      session.dispatch({ type: 'setPaused', paused: false });
      return;
    }
    session.dispatch({ type: 'setPaused', paused: true });
  };

  const duration = carouselDurationMessage(carouselRoundSeconds(slides.map((item) => ({
    dwellSeconds: item.dwellSeconds,
    countsTowardDuration: item.available,
  })), defaultDwell));
  const invalidCount = items.filter((item) => !item.exists || !item.visible).length;
  const hiddenCount = items.filter((item) => (
    item.exists && item.visible && carouselHiddenGroupIds(item.canvas_group_ids, fields.groups).length > 0
  )).length;
  const problemFilter = problemsOnly && (invalidCount > 0 || hiddenCount > 0);
  const shown = items
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => {
      if (!problemFilter) return true;
      const hidden = item.exists && item.visible
        ? carouselHiddenGroupIds(item.canvas_group_ids, fields.groups)
        : [];
      return !item.exists || !item.visible || hidden.length > 0;
    });
  const selectedKeys = useMemo(
    () => [...new Set(items.map((item) => canvasIdentityKey(item.resource_type, item.canvas_id)))],
    [items],
  );
  const previewIndex = player.index >= 0 && player.index < slides.length ? player.index : 0;
  const preview = slides[previewIndex];
  const cachedPreview = preview?.available
    ? readCachedCanvasDetail(preview.resourceType, preview.canvasId)
    : { hit: false as const };
  // revision 本身不参与选帧，只保证撤下保留帧后重绘；帧数据仍留在 ref。
  const stage = resolvePlaybackStage({
    slide: preview,
    ready: session.ready,
    confirmedDetail: session.initialDetail,
    cached: cachedPreview,
    held: heldPlaybackRevision < 0 ? null : heldPlaybackRef.current,
  });
  stageHoldingRef.current = stage.kind === 'frame' && stage.holding;
  if (stage.kind === 'frame' && !stage.holding) {
    heldPlaybackRef.current = { slide: stage.slide, detail: stage.detail };
  }
  playbackSlideKeyRef.current = stage.kind === 'frame' ? stage.slide.key : (preview?.key ?? '');
  const stageResourceType = stage.kind === 'frame' ? stage.slide.resourceType : preview?.resourceType;
  const playableCount = slides.filter((slide) => slide.available).length;
  const positionLabel = slides.length > 0 ? `${previewIndex + 1} / ${slides.length}` : '';
  const positionName = preview?.available && preview.name ? preview.name : '';
  const iconButtonClassName = 'rounded-full! h-8 w-8 min-w-8 flex items-center justify-center';
  const renderTransport = () => {
    const hidePlay = !playbackAllowed;
    const disableStep = slides.length <= 1;
    const step = (direction: 1 | -1) => {
      chooseIndex(manualPreviewStep(slides.length, previewIndex, direction));
    };
    return (
      <>
        <Tooltip title={t('opsCarousel.previous')}>
          <Button
            type="text"
            className={iconButtonClassName}
            aria-label={t('opsCarousel.previous')}
            icon={<LeftOutlined style={{ fontSize: 16 }} />}
            disabled={disableStep}
            onClick={() => step(-1)}
          />
        </Tooltip>
        {!hidePlay && (
          <Tooltip title={player.paused ? t('opsCarousel.play') : t('opsCarousel.pause')}>
            <Button
              type="text"
              className={iconButtonClassName}
              aria-label={player.paused ? t('opsCarousel.play') : t('opsCarousel.pause')}
              icon={player.paused
                ? <CaretRightOutlined style={{ fontSize: 16 }} />
                : <PauseOutlined style={{ fontSize: 16 }} />}
              disabled={playableCount === 0 || slides.length <= 1}
              onClick={togglePlay}
            />
          </Tooltip>
        )}
        <Tooltip title={t('opsCarousel.next')}>
          <Button
            type="text"
            className={iconButtonClassName}
            aria-label={t('opsCarousel.next')}
            icon={<RightOutlined style={{ fontSize: 16 }} />}
            disabled={disableStep}
            onClick={() => step(1)}
          />
        </Tooltip>
      </>
    );
  };
  const positionIndicator = positionLabel ? (
    positionName ? (
      <Tooltip title={positionName}>
        <span className="px-1 text-sm tabular-nums text-[var(--color-text-2)]">{positionLabel}</span>
      </Tooltip>
    ) : (
      <span className="px-1 text-sm tabular-nums text-[var(--color-text-2)]">{positionLabel}</span>
    )
  ) : null;

  if (!carouselId) {
    return (
      <div className="flex h-full items-center justify-center">
        <CompactEmptyState description={t('opsCarousel.emptyList')} />
      </div>
    );
  }

  const renderRow = (item: DraftItem, index: number) => {
    const hidden = !item.exists || !item.visible
      ? []
      : carouselHiddenGroupIds(item.canvas_group_ids, fields.groups);
    const shownPosition = shown.findIndex((row) => row.item.key === item.key);
    const moveUpTarget = displayedMoveTarget(shown.map((row) => row.index), shownPosition, -1);
    const moveDownTarget = displayedMoveTarget(shown.map((row) => row.index), shownPosition, 1);
    return (
      <ItemRow
        key={item.key}
        item={item}
        index={index}
        selected={item.key === preview?.key}
        canEdit={canEdit}
        defaultDwell={defaultDwell}
        hiddenLabels={hidden.map(groupName)}
        canMoveUp={moveUpTarget != null}
        canMoveDown={moveDownTarget != null}
        canMoveTop={index > 0}
        canMoveBottom={index < items.length - 1}
        onActivate={() => chooseIndex(index)}
        onDwell={(value) => {
          setItems((current) => current.map((row) => (
            row.key === item.key ? { ...row, dwell_seconds: value } : row
          )));
        }}
        onMoveUp={() => {
          if (moveUpTarget == null) return;
          setItems((current) => moveItem(current, item.key, moveUpTarget));
        }}
        onMoveDown={() => {
          if (moveDownTarget == null) return;
          setItems((current) => moveItem(current, item.key, moveDownTarget));
        }}
        onMoveTop={() => setItems((current) => moveItem(current, item.key, 0))}
        onMoveBottom={() => setItems((current) => moveItem(current, item.key, current.length - 1))}
        onRemove={() => setItems((current) => current.filter((row) => row.key !== item.key))}
      />
    );
  };

  return (
    <Spin spinning={loading} wrapperClassName="h-full [&_.ant-spin-container]:h-full">
      <div className="flex h-full min-h-0 flex-col overflow-hidden">
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--color-border-1)] px-4 py-2">
          <div className="flex min-w-0 items-center gap-3">
            <span className="truncate text-sm font-medium text-[var(--color-text-1)]">
              {fields.name.trim() || t('opsCarousel.unnamed')}
            </span>
            <span className="shrink-0 text-xs text-[var(--color-text-3)]">
              {t('opsCarousel.roundDuration', undefined, { duration: t(duration.id, undefined, duration.values) })}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {items.length > 0 && renderTransport()}
            {positionIndicator}
            {canEdit && (
              <Tooltip title={t('common.edit')}>
                <Button
                  type="text"
                  className={iconButtonClassName}
                  aria-label={t('common.edit')}
                  icon={<EditOutlined style={{ fontSize: 16 }} />}
                  onClick={openEditor}
                />
              </Tooltip>
            )}
            {canPlay && (
              <Tooltip title={t('common.fullscreen')}>
                <Button
                  type="text"
                  className={iconButtonClassName}
                  aria-label={t('common.fullscreen')}
                  icon={<FullscreenOutlined style={{ fontSize: 16 }} />}
                  disabled={!playbackAllowed || playableCount === 0}
                  onClick={() => { void stageRef.current?.requestFullscreen(); }}
                />
              </Tooltip>
            )}
          </div>
        </div>
        <div
          ref={stageRef}
          className={`relative min-h-0 flex-1 overflow-hidden ${
            stageFullscreen && stageResourceType === 'screen' ? 'bg-slate-950' : 'bg-[var(--color-bg)]'
          }`}
        >
          <ConfigProvider getPopupContainer={stageFullscreen ? fullscreenPopupContainer : undefined}>
          {items.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3">
              <CompactEmptyState description={t('opsCarousel.noItems')} />
              {canEdit && (
                <Button type="primary" icon={<PlusOutlined />} onClick={openEditor}>
                  {t('opsCarousel.addCanvas')}
                </Button>
              )}
            </div>
          ) : stage.kind === 'unavailable' ? (
            <div className="flex h-full items-center justify-center px-6 text-center text-sm text-[var(--color-text-3)]">
              {t('opsCarousel.previewUnavailable')}
            </div>
          ) : stage.kind === 'pending' ? (
            <div className="flex h-full items-center justify-center">
              <Spin />
            </div>
          ) : (
            <div className={`h-full min-h-0 w-full ${stage.slide.resourceType === 'screen' ? 'overflow-hidden' : 'overflow-auto'}`}>
              <PlaybackSlideFrame
                key={stage.shellKey}
                slide={stage.slide}
                initialDetail={stage.detail}
                presentFullscreen={stageFullscreen && stage.slide.resourceType === 'screen'}
                onError={onPlaybackFrameError}
              />
            </div>
          )}
          {stageFullscreen && (
            <CarouselFullscreenChrome
              visible={controlsVisible}
              paused={player.paused}
              slides={slides}
              index={player.index}
              remainingMs={player.remainingMs}
              remainingClock={session.remainingClock}
              previousLabel={t('opsCarousel.previous')}
              nextLabel={t('opsCarousel.next')}
              playLabel={t('opsCarousel.play')}
              pauseLabel={t('opsCarousel.pause')}
              resumeHint={t('opsCarousel.spaceToResume')}
              disableStep={playableCount <= 1}
              disablePlay={playableCount === 0 || slides.length <= 1}
              onPrevious={() => session.dispatch({ type: 'prev' })}
              onNext={() => session.dispatch({ type: 'next' })}
              onTogglePlay={togglePlay}
              onHoverChange={(hovering) => {
                if (hotzoneHoverRef.current === hovering) return;
                hotzoneHoverRef.current = hovering;
                applyChromePlanRef.current(hovering ? 'hotzone-enter' : 'hotzone-leave');
              }}
            />
          )}
          </ConfigProvider>
        </div>
      </div>
      <OperateFormDrawer
        title={t('common.edit')}
        open={editorOpen}
        width={640}
        destroyOnClose={false}
        onClose={requestClose}
        onCancel={requestClose}
        onConfirm={() => { void persist(); }}
        confirmLoading={saving}
        confirmText={t('common.save')}
        cancelText={t('common.cancel')}
        primaryFirst={false}
        styles={{ body: { overflow: 'hidden', display: 'flex', flexDirection: 'column' } }}
      >
        <div className="flex h-full min-h-0 flex-1 flex-col">
          <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
            <span className="text-sm text-[var(--color-text-2)]">{t('opsCarousel.defaultDwell')}</span>
            <InputNumber
              min={CAROUSEL_DWELL_MIN_SECONDS}
              max={CAROUSEL_DWELL_MAX_SECONDS}
              value={fields.defaultDwell ?? undefined}
              className="w-32"
              addonAfter={t('opsCarousel.seconds')}
              onChange={(value) => setFields((current) => ({
                ...current,
                defaultDwell: value == null ? null : clampCarouselDwellSeconds(value),
              }))}
            />
          </div>
          <div className="mb-2 flex shrink-0 items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-[var(--color-text-1)]">
                {t('opsCarousel.items')} ({items.length}/{CAROUSEL_MAX_ITEMS})
              </div>
              <div className="text-xs text-[var(--color-text-3)]">
                {t('opsCarousel.dwellEmptyHint', undefined, { seconds: defaultDwell })}
              </div>
            </div>
            {canEdit && (
              <Button icon={<PlusOutlined />} onClick={() => { void openPicker(); }}>
                {t('opsCarousel.addCanvas')}
              </Button>
            )}
          </div>
          {(invalidCount > 0 || hiddenCount > 0) && (
            <Alert
              className="mb-3 shrink-0"
              type="warning"
              showIcon
              message={t('opsCarousel.issueSummary', undefined, { invalid: invalidCount, hidden: hiddenCount })}
              action={(
                <div className="flex gap-2">
                  <Button size="small" onClick={() => setProblemsOnly((value) => !value)}>
                    {problemFilter ? t('opsCarousel.showAll') : t('opsCarousel.problemsOnly')}
                  </Button>
                  {canEdit && invalidCount > 0 && (
                    <Button
                      size="small"
                      danger
                      onClick={() => setItems((current) => current.filter((item) => item.exists && item.visible))}
                    >
                      {t('opsCarousel.removeInvalid')}
                    </Button>
                  )}
                </div>
              )}
            />
          )}
          <div className="min-h-0 flex-1 overflow-auto">
            {shown.length === 0 ? (
              <CompactEmptyState description={t('opsCarousel.noItems')} />
            ) : (
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragStart={() => { dragging.current = true; }}
                onDragEnd={(event: DragEndEvent) => {
                  window.setTimeout(() => { dragging.current = false; }, 0);
                  if (!canEdit) return;
                  const { active, over } = event;
                  if (!over || active.id === over.id) return;
                  setItems((current) => {
                    const from = current.findIndex((item) => item.key === active.id);
                    const to = current.findIndex((item) => item.key === over.id);
                    if (from < 0 || to < 0) return current;
                    return arrayMove(current, from, to);
                  });
                }}
                onDragCancel={() => { dragging.current = false; }}
              >
                <SortableContext items={shown.map(({ item }) => item.key)} strategy={verticalListSortingStrategy}>
                  <div>{shown.map(({ item, index }) => renderRow(item, index))}</div>
                </SortableContext>
              </DndContext>
            )}
          </div>
        </div>
      </OperateFormDrawer>
      <CanvasPicker
        open={pickerOpen}
        directories={directories}
        selectedKeys={selectedKeys}
        currentItems={items.map((item) => ({ resourceType: item.resource_type, canvasId: item.canvas_id }))}
        loadFailed={treeLoadFailed}
        onClose={() => setPickerOpen(false)}
        onConfirm={applyPicked}
      />
    </Spin>
  );
});

CarouselEditor.displayName = 'CarouselEditor';

export default CarouselEditor;
