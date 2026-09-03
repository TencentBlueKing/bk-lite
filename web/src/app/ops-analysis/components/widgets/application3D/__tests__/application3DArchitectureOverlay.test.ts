import * as THREE from 'three';
import { describe, expect, it } from 'vitest';
import { UNKNOWN_STATUS_BADGE } from '../application3DLayout';
import {
  ARCH_HOST_OVERLAY_GAP,
  ARCH_HOST_OVERLAY_SIZE,
  expandArchitectureCabinetWorldBox,
  formatArchitectureHostAlarmCount,
  formatArchitectureHostSeverity,
  formatArchitectureHostState,
  overlayScreenRect,
  placeOverlayOutsideRect,
  projectWorldBoxToScreenRect,
  screenRectsIntersect,
  type ScreenRect,
} from '../application3DArchitectureOverlay';

const compactViewport = { width: 320, height: 180 };
const boardViewport = { width: 960, height: 540 };
const overlay = ARCH_HOST_OVERLAY_SIZE;

const hostAt = (left: number, top: number, width = 40, height = 60): ScreenRect => ({
  left,
  top,
  right: left + width,
  bottom: top + height,
});

const leftoverOnSide = (side: 'right' | 'left' | 'above' | 'below', host: ScreenRect, viewport: { width: number; height: number }) => {
  if (side === 'right') return viewport.width - host.right;
  if (side === 'left') return host.left;
  if (side === 'above') return host.top;
  return viewport.height - host.bottom;
};

describe('placeOverlayOutsideRect', () => {
  it('places a slightly-right-of-center host on its right when that side fits', () => {
    const host = hostAt(510, 220, 48, 72);
    expect(leftoverOnSide('left', host, boardViewport)).toBeGreaterThan(
      leftoverOnSide('right', host, boardViewport),
    );
    const placed = placeOverlayOutsideRect(host, overlay, boardViewport, ARCH_HOST_OVERLAY_GAP);
    expect(placed.side).toBe('right');
    expect(placed.left).toBeCloseTo(host.right + ARCH_HOST_OVERLAY_GAP);
    expect(placed.left + overlay.width).toBeLessThanOrEqual(boardViewport.width);
    expect(
      screenRectsIntersect(overlayScreenRect(placed, overlay), host),
    ).toBe(false);
  });

  it('falls back without covering a host at the right canvas edge', () => {
    const host = hostAt(918, 230, 36, 70);
    const placed = placeOverlayOutsideRect(host, overlay, boardViewport, ARCH_HOST_OVERLAY_GAP);
    expect(placed.side).not.toBe('right');
    expect(['left', 'above', 'below']).toContain(placed.side);
    expect(placed.left).toBeGreaterThanOrEqual(0);
    expect(placed.top).toBeGreaterThanOrEqual(0);
    expect(placed.left + overlay.width).toBeLessThanOrEqual(boardViewport.width);
    expect(placed.top + overlay.height).toBeLessThanOrEqual(boardViewport.height);
    expect(
      screenRectsIntersect(overlayScreenRect(placed, overlay), host),
    ).toBe(false);
  });

  it('does not rank sides by leftover viewport space', () => {
    const host = hostAt(490, 510, 40, 20);
    expect(leftoverOnSide('above', host, boardViewport)).toBeGreaterThan(
      leftoverOnSide('left', host, boardViewport),
    );
    expect(leftoverOnSide('left', host, boardViewport)).toBeGreaterThan(
      leftoverOnSide('right', host, boardViewport),
    );
    const placed = placeOverlayOutsideRect(host, overlay, boardViewport, ARCH_HOST_OVERLAY_GAP);
    expect(placed.side).toBe('right');
    expect(placed.left).toBeCloseTo(host.right + ARCH_HOST_OVERLAY_GAP);
  });

  it('uses right → left → above → below when earlier sides do not fit', () => {
    const host = hostAt(90, 140, 140, 28);
    const placed = placeOverlayOutsideRect(host, overlay, compactViewport, ARCH_HOST_OVERLAY_GAP);
    expect(placed.side).toBe('above');
    expect(placed.top + overlay.height).toBeCloseTo(host.top - ARCH_HOST_OVERLAY_GAP);
    expect(
      screenRectsIntersect(overlayScreenRect(placed, overlay), host),
    ).toBe(false);
  });

  it('places below when the host sits at the top and sides do not fit', () => {
    const host = hostAt(120, 8, 80, 40);
    const placed = placeOverlayOutsideRect(host, overlay, compactViewport, ARCH_HOST_OVERLAY_GAP);
    expect(placed.side).toBe('below');
    expect(placed.top).toBeCloseTo(host.bottom + ARCH_HOST_OVERLAY_GAP);
    expect(
      screenRectsIntersect(overlayScreenRect(placed, overlay), host),
    ).toBe(false);
  });

  it('clamps to the canvas without covering the host', () => {
    const host = hostAt(8, 4, 36, 40);
    const placed = placeOverlayOutsideRect(host, overlay, compactViewport, ARCH_HOST_OVERLAY_GAP);
    expect(placed.left).toBeGreaterThanOrEqual(0);
    expect(placed.top).toBeGreaterThanOrEqual(0);
    expect(placed.left + overlay.width).toBeLessThanOrEqual(compactViewport.width);
    expect(placed.top + overlay.height).toBeLessThanOrEqual(compactViewport.height);
    expect(
      screenRectsIntersect(overlayScreenRect(placed, overlay), host),
    ).toBe(false);
  });

  it('keeps an 8–12px gap on the chosen side when space allows', () => {
    const host = hostAt(24, 50);
    const placed = placeOverlayOutsideRect(host, overlay, compactViewport);
    expect(ARCH_HOST_OVERLAY_GAP).toBeGreaterThanOrEqual(8);
    expect(ARCH_HOST_OVERLAY_GAP).toBeLessThanOrEqual(12);
    expect(placed.left - host.right).toBe(ARCH_HOST_OVERLAY_GAP);
  });
});

describe('architecture cabinet overlay AABB', () => {
  const makeRackGroup = () => {
    const group = new THREE.Group();
    group.userData.archRole = 'rack-root';
    const chassis = new THREE.Mesh(new THREE.BoxGeometry(0.32, 1.08, 0.32));
    chassis.userData.archRole = 'rack';
    const led = new THREE.Mesh(new THREE.SphereGeometry(0.02, 8, 8));
    led.userData.archRole = 'rack-led';
    led.position.set(0, 0.4, 0.17);
    const stroke = new THREE.Mesh(new THREE.BoxGeometry(0.34, 1.1, 0.34));
    stroke.userData.archRole = 'rack-stroke';
    const label = new THREE.Mesh(new THREE.PlaneGeometry(1, 1));
    label.userData.archRole = 'node-label';
    label.scale.set(Math.max(0.32 * 3.6, 1.4), 0.36, 1);
    label.position.set(0, 0.82, 0);
    group.add(chassis, led, stroke, label);
    group.updateWorldMatrix(true, true);
    return { group, chassis, stroke, label };
  };

  it('builds the host AABB from cabinet meshes and ignores the name plate', () => {
    const { group } = makeRackGroup();
    const cabinetBox = expandArchitectureCabinetWorldBox(group);
    const fullBox = new THREE.Box3().setFromObject(group);
    expect(cabinetBox.max.x - cabinetBox.min.x).toBeCloseTo(0.34, 5);
    expect(fullBox.max.x - fullBox.min.x).toBeCloseTo(1.4, 5);
    expect(cabinetBox.max.x - cabinetBox.min.x).toBeLessThan(0.5);
    expect(fullBox.max.x - fullBox.min.x).toBeGreaterThan(1);
  });

  it('does not fall back to the name plate when cabinet meshes are absent', () => {
    const group = new THREE.Group();
    const label = new THREE.Mesh(new THREE.PlaneGeometry(1, 1));
    label.userData.archRole = 'node-label';
    label.scale.set(1.4, 0.36, 1);
    group.add(label);
    group.updateWorldMatrix(true, true);
    const box = expandArchitectureCabinetWorldBox(group);
    expect(box.isEmpty()).toBe(true);
  });

  it('projects the cabinet AABB in the passed CSS viewport, not a transformed rect', () => {
    const { group } = makeRackGroup();
    const cabinetBox = expandArchitectureCabinetWorldBox(group);
    const camera = new THREE.OrthographicCamera(-2, 2, 1.125, -1.125, 0.1, 10);
    camera.position.set(0, 0, 5);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
    const cssRect = projectWorldBoxToScreenRect(cabinetBox, camera, boardViewport);
    const scaledRect = projectWorldBoxToScreenRect(cabinetBox, camera, {
      width: boardViewport.width / 2,
      height: boardViewport.height / 2,
    });
    expect(cssRect.right - cssRect.left).toBeCloseTo((scaledRect.right - scaledRect.left) * 2, 5);
    expect(cssRect.left).not.toBeCloseTo(scaledRect.left, 0);
    const placed = placeOverlayOutsideRect(cssRect, overlay, boardViewport, ARCH_HOST_OVERLAY_GAP);
    expect(placed.side).toBe('right');
    expect(placed.left).toBeCloseTo(cssRect.right + ARCH_HOST_OVERLAY_GAP);
    expect(
      screenRectsIntersect(overlayScreenRect(placed, overlay), cssRect),
    ).toBe(false);
  });
});

describe('architecture host overlay copy', () => {
  const t = (_id: string, fallback = '') => fallback;

  it('reuses application3D status labels for health.state', () => {
    expect(formatArchitectureHostState('normal', t)).toBe('运行正常');
    expect(formatArchitectureHostState('alarming', t)).toBe('告警');
    expect(formatArchitectureHostState('unknown', t)).toBe('状态未知');
  });

  it('shows the wall unknown glyph when count or severity is missing', () => {
    expect(formatArchitectureHostAlarmCount(null)).toBe(UNKNOWN_STATUS_BADGE);
    expect(formatArchitectureHostAlarmCount(4)).toBe('4');
    expect(formatArchitectureHostSeverity(null)).toBe(UNKNOWN_STATUS_BADGE);
    expect(formatArchitectureHostSeverity('严重')).toBe('严重');
  });
});
