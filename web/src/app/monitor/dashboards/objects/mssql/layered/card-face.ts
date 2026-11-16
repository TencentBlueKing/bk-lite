export type MssqlCardFace = 'loading' | 'empty' | 'ready';

/** 同一张卡只处在加载中、空态、有数三者之一。查询进行中优先加载中。 */
export function mssqlCardFace(loading: boolean, hasData: boolean): MssqlCardFace {
  if (loading) return 'loading';
  if (!hasData) return 'empty';
  return 'ready';
}
