export type FitViewAlign = 'center' | 'start';

export interface FitViewOptions {
  padding?: number;
  maxScale?: number;
  minScale?: number;
  /** start：内容贴齐画布左上，层标签才不会和节点错位 */
  align?: FitViewAlign;
}

/** zoomToFit 之后把内容左缘挪到 padding，避免居中在窄容器里挤出右边。 */
export function startAlignTranslateX(params: {
  contentX: number;
  scale: number;
  translateX: number;
  padding: number;
}): number {
  const screenX = params.contentX * params.scale + params.translateX;
  return params.translateX + (params.padding - screenX);
}
