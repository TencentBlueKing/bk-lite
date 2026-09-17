/** 网络设备仪表盘「不可用哨兵」契约：插件 metrics.json 为权威，按 collect_type 选用。 */

export type UnavailableMeaning = 'no_sensor' | 'no_module' | 'unsupported' | 'empty_slot';

export type SentinelPolicy = 'keep_for_display' | 'drop_at_query';

export type DashboardAggregate = 'max' | 'min';

/**
 * 单条契约：某一 collect_type × metric 的哨兵语义与看板查询构造输入。
 * sentinels / valueExpr 须与 evidence 指向的插件 metrics.json 一致，由 CI 双向校验。
 */
export interface MetricUnavailableContract {
  metric: string;
  collectType: string;
  sentinels: number[];
  meaning: UnavailableMeaning;
  displayLabel: string;
  guideDetail: string;
  /** 已含哨兵过滤（及必要换算）的内层表达式，使用 __$labels__ 占位。 */
  valueExpr: string;
  /**
   * keep_for_display 时 or 回退的原始序列（通常未过滤哨兵）。
   * drop_at_query 可不填。
   */
  rawExpr?: string;
  aggregate: DashboardAggregate;
  sentinelPolicy: SentinelPolicy;
  scaleNote?: string;
  /** 相对仓库根的插件 metrics.json 路径，供校验与审计。 */
  evidence: string;
}
