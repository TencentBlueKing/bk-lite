export type CardAlertFold = 'solid' | 'outline';

/** 折角默认实心。只有调用方显式 fold="outline" 才描边，主值色不参与。 */
export const seriesFoldOutline = (fold?: CardAlertFold) => fold === 'outline';
