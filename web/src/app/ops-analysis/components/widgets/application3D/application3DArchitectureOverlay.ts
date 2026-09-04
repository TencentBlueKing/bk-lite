import * as THREE from 'three';
import type { Application3DArchitectureNode } from '@/app/ops-analysis/types/sceneWidget';
import {
  UNKNOWN_STATUS_BADGE,
  type Application3DTranslate,
} from './application3DLayout';

export interface ScreenRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface ScreenSize {
  width: number;
  height: number;
}

export type ArchitectureOverlaySide = 'right' | 'left' | 'above' | 'below';

export interface ArchitectureHostSelection {
  node: Application3DArchitectureNode;
  hostScreenRect: ScreenRect;
  overlay: { left: number; top: number };
}

/** Keep in sync with `.app3d-arch-host-chip` in application3DChrome.css. */
export const ARCH_HOST_OVERLAY_SIZE = { width: 176, height: 96 } as const;
export const ARCH_HOST_OVERLAY_GAP = 10;

const SIDES: ArchitectureOverlaySide[] = ['right', 'left', 'above', 'below'];

export const screenRectsIntersect = (a: ScreenRect, b: ScreenRect) =>
  a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;

export const overlayScreenRect = (
  position: { left: number; top: number },
  size: ScreenSize = ARCH_HOST_OVERLAY_SIZE,
): ScreenRect => ({
  left: position.left,
  top: position.top,
  right: position.left + size.width,
  bottom: position.top + size.height,
});

const placeOnSide = (
  side: ArchitectureOverlaySide,
  host: ScreenRect,
  overlay: ScreenSize,
  gap: number,
) => {
  const midX = (host.left + host.right) / 2;
  const midY = (host.top + host.bottom) / 2;
  if (side === 'right') {
    return { left: host.right + gap, top: midY - overlay.height / 2 };
  }
  if (side === 'left') {
    return { left: host.left - gap - overlay.width, top: midY - overlay.height / 2 };
  }
  if (side === 'above') {
    return { left: midX - overlay.width / 2, top: host.top - gap - overlay.height };
  }
  return { left: midX - overlay.width / 2, top: host.bottom + gap };
};

const clampOverlay = (
  position: { left: number; top: number },
  overlay: ScreenSize,
  viewport: ScreenSize,
) => ({
  left: Math.min(Math.max(position.left, 0), Math.max(0, viewport.width - overlay.width)),
  top: Math.min(Math.max(position.top, 0), Math.max(0, viewport.height - overlay.height)),
});

/**
 * Place a compact overlay outside the host cabinet screen AABB.
 * Tries right → left → above → below and takes the first side that stays
 * inside the viewport after clamp without covering the cabinet.
 */
export const placeOverlayOutsideRect = (
  host: ScreenRect,
  overlay: ScreenSize = ARCH_HOST_OVERLAY_SIZE,
  viewport: ScreenSize,
  gap = ARCH_HOST_OVERLAY_GAP,
): { left: number; top: number; side: ArchitectureOverlaySide } => {
  for (const side of SIDES) {
    const clamped = clampOverlay(placeOnSide(side, host, overlay, gap), overlay, viewport);
    if (!screenRectsIntersect(overlayScreenRect(clamped, overlay), host)) {
      return { ...clamped, side };
    }
  }
  const fallback = SIDES[0];
  const clamped = clampOverlay(placeOnSide(fallback, host, overlay, gap), overlay, viewport);
  return { ...clamped, side: fallback };
};

export const projectWorldBoxToScreenRect = (
  box: THREE.Box3,
  camera: THREE.Camera,
  viewport: ScreenSize,
): ScreenRect => {
  const point = new THREE.Vector3();
  let left = Infinity;
  let top = Infinity;
  let right = -Infinity;
  let bottom = -Infinity;
  for (const x of [box.min.x, box.max.x]) {
    for (const y of [box.min.y, box.max.y]) {
      for (const z of [box.min.z, box.max.z]) {
        point.set(x, y, z).project(camera);
        const sx = (point.x * 0.5 + 0.5) * viewport.width;
        const sy = (-point.y * 0.5 + 0.5) * viewport.height;
        left = Math.min(left, sx);
        right = Math.max(right, sx);
        top = Math.min(top, sy);
        bottom = Math.max(bottom, sy);
      }
    }
  }
  return { left, top, right, bottom };
};

const cabinetPartBox = new THREE.Box3();

const isArchitectureCabinetOverlayMesh = (object: THREE.Object3D) => {
  if (!(object as THREE.Mesh).isMesh) return false;
  return object.userData.archRole !== 'node-label';
};

/**
 * World AABB of the rack chassis (hull, LEDs, alarm stroke). Skips the
 * billboard name plate so overlay attach uses the cabinet, not the label.
 */
export const expandArchitectureCabinetWorldBox = (
  root: THREE.Object3D,
  target = new THREE.Box3(),
) => {
  target.makeEmpty();
  root.updateWorldMatrix(true, true);
  root.traverse((child) => {
    if (!isArchitectureCabinetOverlayMesh(child)) return;
    const mesh = child as THREE.Mesh;
    const geometry = mesh.geometry;
    if (!geometry) return;
    if (!geometry.boundingBox) geometry.computeBoundingBox();
    if (!geometry.boundingBox) return;
    cabinetPartBox.copy(geometry.boundingBox).applyMatrix4(mesh.matrixWorld);
    target.union(cabinetPartBox);
  });
  return target;
};

export const formatArchitectureHostState = (
  state: string | undefined,
  t: Application3DTranslate,
) => {
  if (state === 'normal') return t('dashboard.application3DStatus_normal', '运行正常');
  if (state === 'alarming') return t('dashboard.application3DStatus_alarming', '告警');
  return t('dashboard.application3DStatus_unknown', '状态未知');
};

export const formatArchitectureHostAlarmCount = (count: number | null | undefined) =>
  count == null ? UNKNOWN_STATUS_BADGE : String(count);

export const formatArchitectureHostSeverity = (label: string | null | undefined) =>
  label?.trim() ? label : UNKNOWN_STATUS_BADGE;
