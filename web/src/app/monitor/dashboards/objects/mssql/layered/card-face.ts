export type MssqlCardFace = 'loading' | 'empty' | 'ready';

/** 同一张卡只处在加载中、空态、有数三者之一。查询进行中优先加载中。 */
export function mssqlCardFace(loading: boolean, hasData: boolean): MssqlCardFace {
  if (loading) return 'loading';
  if (!hasData) return 'empty';
  return 'ready';
}

/**
 * 这张卡还没有点时，自己的查询未结束，或同一批还有别的查询未结束，都继续显示加载中。
 * 整批结束后才允许空态，避免先返回的空结果和仍在加载的卡叠在一起。
 * 已经有点的卡不推迟，0 也算有点。
 */
export function mssqlDeferEmpty(
  hasData: boolean,
  ownPending: boolean,
  batchLoading: boolean
): boolean {
  if (hasData) return false;
  return ownPending || batchLoading;
}
