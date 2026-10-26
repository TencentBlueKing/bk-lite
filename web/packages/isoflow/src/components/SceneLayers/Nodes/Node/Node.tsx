import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Box, Typography, Stack } from '@mui/material';
import {
  PROJECTED_TILE_SIZE,
  DEFAULT_LABEL_HEIGHT,
  DEFAULT_NODE_NAME,
  MARKDOWN_EMPTY_VALUE
} from 'src/config';
import { getTilePosition } from 'src/utils';
import { useIcon } from 'src/hooks/useIcon';
import { ViewItem } from 'src/types';
import { useModelItem } from 'src/hooks/useModelItem';
import { ALERT_BADGE_TONE, NODE_STATUS_COLOR } from 'src/diagramOverlay/colors';
import { CORNER_BADGE_SX } from 'src/diagramOverlay/cornerBadge';
import { useDiagramVisual } from 'src/diagramOverlay/context';
import { visibleMetricLines } from 'src/diagramOverlay/metricCard';
import type { NodeMetricLine, NodeStatusLevel } from 'src/types';
import { useUiStateStore } from 'src/stores/uiStateStore';
import { useLabels } from 'src/hooks/useLabels';
import { ExpandableLabel } from 'src/components/Label/ExpandableLabel';
import { LabelConnector } from 'src/components/Label/Label';
import { MarkdownEditor } from 'src/components/MarkdownEditor/MarkdownEditor';
import { NodeStatusMark } from './NodeStatusMark';

// Decorative air between the saved label height and the icon. Not stored.
const LABEL_ICON_GAP = 12;
const PLATE_DETAIL_MIN_ZOOM = 0.7;

const PLATE_LABEL_TONE: Partial<
  Record<NodeStatusLevel, { bg: string; fg: string; border: string }>
> = {
  unmonitored: {
    bg: 'var(--color-fill-3)',
    fg: 'var(--color-text-3)',
    border: '1px solid var(--color-text-4)'
  },
  unknown: {
    bg: 'var(--color-fill-3)',
    fg: 'var(--color-text-3)',
    border: '1px solid var(--color-text-4)'
  },
  forbidden: {
    bg: 'var(--color-fill-3)',
    fg: 'var(--color-text-3)',
    border: '1px solid var(--color-text-4)'
  },
  invalid: {
    bg: 'color-mix(in srgb, var(--color-fail) 12%, transparent)',
    fg: 'var(--color-fail)',
    border: '1px solid color-mix(in srgb, var(--color-fail) 35%, transparent)'
  }
};

export const NodeLabelLayerContext = createContext<HTMLElement | null>(null);

/** Icon under the pointer. Geometry hit, so the icon itself stays pointer-events none. */
export const HoveredIconContext = createContext<string | null>(null);

const MetricLines = ({ lines, pinned }: { lines: NodeMetricLine[]; pinned: boolean }) => (
  <Box
    data-testid="architecture-metric-card"
    data-metric-pinned={pinned ? 'true' : 'false'}
    sx={{
      display: 'flex',
      flexDirection: 'column',
      gap: '1px',
      minWidth: 0,
      maxWidth: 220
    }}
  >
    {lines.map((line, index) => (
      <Box
        key={`${line.name}-${index}`}
        sx={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: '8px',
          minWidth: 0
        }}
      >
        <Box
          component="span"
          sx={{
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            color: 'var(--color-text-3)',
            fontSize: 11,
            lineHeight: 1.45
          }}
        >
          {line.name}
        </Box>
        <Box
          component="span"
          sx={{
            flexShrink: 0,
            color: 'var(--color-text-1)',
            fontSize: 11,
            fontWeight: 600,
            lineHeight: 1.45,
            fontVariantNumeric: 'tabular-nums',
            whiteSpace: 'nowrap'
          }}
        >
          {line.text}
        </Box>
      </Box>
    ))}
  </Box>
);

interface Props {
  node: ViewItem;
  order: number;
}

export const Node = ({ node, order }: Props) => {
  const modelItem = useModelItem(node.id);
  const visual = useDiagramVisual();
  const status = visual.nodeStatus?.[node.id];
  const zoom = useUiStateStore((state) => state.zoom);
  const metricEntry = visual.nodeMetrics?.[node.id];
  const metricSource = metricEntry?.lines ?? [];
  const [hovering, setHovering] = useState(false);
  const hoverTimer = useRef<number | null>(null);
  const setHovered = (next: boolean) => {
    if (hoverTimer.current !== null) window.clearTimeout(hoverTimer.current);
    if (next) {
      setHovering(true);
      return;
    }
    hoverTimer.current = window.setTimeout(() => setHovering(false), 80);
  };
  useEffect(() => {
    return () => {
      if (hoverTimer.current !== null) window.clearTimeout(hoverTimer.current);
    };
  }, []);
  const { iconComponent } = useIcon(modelItem.icon, {
    id: node.id,
    order
  });

  const position = useMemo(() => {
    return getTilePosition({
      tile: node.tile,
      origin: 'BOTTOM'
    });
  }, [node.tile]);

  const labels = useLabels();
  const plateTitle = status?.plateTitle?.trim() || '';
  const storedName =
    modelItem.name === DEFAULT_NODE_NAME ? labels.untitledNode : modelItem.name;
  const title = plateTitle || storedName;
  const viewing = visual.editorMode === 'EXPLORABLE_READONLY';
  const plateMark = viewing ? status?.plateMark?.trim() || '' : '';
  const healthyDot = viewing && status?.level === 'normal';
  const markTone = status?.level ? ALERT_BADGE_TONE[status.level] : undefined;
  const labelTone = status?.level ? PLATE_LABEL_TONE[status.level] : undefined;
  // Alert counts sit on the plate's corner; short status labels stay inline.
  const cornerMark = plateMark && markTone ? plateMark : '';
  const inlineMark = plateMark && !markTone && labelTone ? plateMark : '';
  const subtitle = status?.plateSubtitle?.trim() || '';
  const showSubtitle = Boolean(subtitle) && zoom >= PLATE_DETAIL_MIN_ZOOM;
  const hoveredIconId = useContext(HoveredIconContext);
  const labelRaised = hovering || hoveredIconId === node.id;
  const revealed = viewing && labelRaised;
  const metricsPinned = metricEntry?.pinned !== false;
  const showMetrics = visibleMetricLines({
    editorMode: visual.editorMode,
    zoom,
    pinned: metricsPinned,
    hovering: revealed,
    lineCount: metricSource.length
  });
  const metricLines = showMetrics ? metricSource : [];
  const resourceName = status?.hoverName?.trim() || '';
  const modelName = status?.hoverModel?.trim() || '';
  const unnamedReason =
    !resourceName &&
    (status?.level === 'forbidden' || status?.level === 'invalid')
      ? status?.hint?.trim() || ''
      : '';
  const quietReason = revealed && !resourceName ? unnamedReason : '';
  // Model type rides the name line, one shade quieter: `redis-order-01 (Redis)`.
  const modelSuffix = modelName && modelName !== title ? ` (${modelName})` : '';
  const labelHeight = (node.labelHeight ?? DEFAULT_LABEL_HEIGHT) + LABEL_ICON_GAP;
  // View mode: the card and its corner badge open the icon on click.
  // order is -(x + y). Negating it keeps the front plate above the icon and any plate behind it.
  const plateHit = viewing
    ? { 'data-icon-hit': node.id, 'data-icon-order': 1_000_000 - order }
    : undefined;
  const labelLayer = useContext(NodeLabelLayerContext);

  const description = useMemo(() => {
    if (
      modelItem.description === undefined ||
      modelItem.description === MARKDOWN_EMPTY_VALUE
    )
      return null;

    return modelItem.description;
  }, [modelItem.description]);

  const plate =
    title || description || showSubtitle || inlineMark || healthyDot || cornerMark ? (
      <Box
        data-plate-subtitle={showSubtitle ? subtitle : ''}
        data-plate-expanded={quietReason ? 'true' : 'false'}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        sx={{ position: 'absolute', pointerEvents: 'auto', zIndex: labelRaised ? 3 : 0 }}
        style={{ left: position.x, top: position.y }}
      >
        <Box
          sx={{ position: 'absolute' }}
          style={{ bottom: PROJECTED_TILE_SIZE.height / 2 }}
        >
          <ExpandableLabel
            maxWidth={480}
            expandDirection="BOTTOM"
            labelHeight={labelHeight}
            hideConnector={Boolean(labelLayer)}
            uncapped={metricLines.length > 0 || Boolean(quietReason)}
            sx={{ py: '3px', px: '5px', borderRadius: '4px' }}
            cardProps={plateHit}
            cornerBadge={
              cornerMark && markTone ? (
                <Box
                  component="span"
                  {...plateHit}
                  title={status?.badgeHint || status?.hint || undefined}
                  data-plate-mark={status?.level}
                  sx={CORNER_BADGE_SX}
                  style={{ backgroundColor: markTone.bg, color: markTone.fg }}
                >
                  {cornerMark}
                </Box>
              ) : null
            }
          >
            <Stack spacing={0.25}>
              {(title || inlineMark || healthyDot) && (
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    minWidth: 0
                  }}
                >
                  {title ? (
                    <Typography
                      sx={{
                        minWidth: 0,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        fontSize: 12,
                        fontWeight: 600,
                        lineHeight: 1.2,
                        color: 'var(--color-text-1)'
                      }}
                    >
                      {title}
                      {modelSuffix ? (
                        <Box
                          component="span"
                          data-testid="architecture-model-suffix"
                          sx={{ color: 'var(--color-text-3)', fontWeight: 400 }}
                        >
                          {modelSuffix}
                        </Box>
                      ) : null}
                    </Typography>
                  ) : null}
                  {healthyDot ? (
                    <Box
                      component="span"
                      title={status?.hint || undefined}
                      data-plate-mark="normal"
                      sx={{
                        flexShrink: 0,
                        alignSelf: 'center',
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        bgcolor: NODE_STATUS_COLOR.normal
                      }}
                    />
                  ) : null}
                  {inlineMark && labelTone ? (
                    <Box
                      component="span"
                      title={status?.hint || undefined}
                      data-plate-mark={status?.level}
                      sx={{
                        flexShrink: 0,
                        display: 'inline-flex',
                        alignItems: 'center',
                        boxSizing: 'border-box',
                        height: 18,
                        px: '6px',
                        borderRadius: '4px',
                        border: labelTone.border,
                        bgcolor: labelTone.bg,
                        color: labelTone.fg,
                        fontSize: 11,
                        fontWeight: 500,
                        lineHeight: 1,
                        letterSpacing: '0.02em',
                        whiteSpace: 'nowrap'
                      }}
                    >
                      {inlineMark}
                    </Box>
                  ) : null}
                </Box>
              )}
              {/* Pinned (开关打开) metrics stay fixed under the name even on hover;
                  only the unpinned hover reveal moves them below the divider. */}
              {(!revealed || metricsPinned) && metricLines.length > 0 ? (
                <MetricLines lines={metricLines} pinned={metricsPinned} />
              ) : null}
              {quietReason ? (
                <Typography
                  data-testid="architecture-resource-hover"
                  sx={{ color: 'var(--color-text-3)', fontSize: 11, lineHeight: 1.35 }}
                >
                  {quietReason}
                </Typography>
              ) : showSubtitle ? (
                <Typography sx={{ color: 'var(--color-text-3)', fontSize: 11, lineHeight: 1.3 }}>
                  {subtitle}
                </Typography>
              ) : null}
              {revealed && !metricsPinned && metricLines.length > 0 ? (
                <>
                  <Box
                    data-testid="architecture-metric-divider"
                    sx={{ borderTop: '1px solid var(--color-border-1)', my: '2px' }}
                  />
                  <MetricLines lines={metricLines} pinned={false} />
                </>
              ) : null}
              {description ? (
                <MarkdownEditor
                  value={description}
                  onChange={() => {}}
                  readOnly
                />
              ) : null}
            </Stack>
          </ExpandableLabel>
        </Box>
      </Box>
    ) : null;

  return (
    <Box
      sx={{
        position: 'absolute',
        zIndex: order
      }}
    >
      {labelLayer ? createPortal(plate, labelLayer) : plate}
      <Box
        sx={{ position: 'absolute' }}
        style={{
          left: position.x,
          top: position.y
        }}
      >
        {/* The dotted connector stays in the icon layer, so the icon covers it. */}
        {plate && labelLayer ? (
          <Box
            sx={{ position: 'absolute' }}
            style={{ bottom: PROJECTED_TILE_SIZE.height / 2 }}
          >
            <LabelConnector labelHeight={labelHeight} />
          </Box>
        ) : null}
        <NodeStatusMark nodeId={node.id} order={order} part="outline" />
        {iconComponent && (
          <Box
            sx={{
              position: 'absolute',
              pointerEvents: 'none'
            }}
          >
            {iconComponent}
          </Box>
        )}
        <NodeStatusMark nodeId={node.id} order={order} />
      </Box>
    </Box>
  );
};
