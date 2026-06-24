'use client';

import React from 'react';
import {
  ApiOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  NodeIndexOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import MetricViews from '@/app/monitor/components/metric-views';
import {
  StatCard,
  CollectionStatusCard,
  TitleWithGuide,
  DashboardPageHeader,
  DashboardInstanceCard,
  RingChartPanel,
  HorizontalBarPanel,
  TrendChartPanel
} from '../../shared/widgets';
import {
  SummaryCardConfig,
  SimpleDashboardConfig,
  useSimpleDashboardData
} from './simple-dashboard-core';
import styles from './simple-dashboard.module.scss';

const getIcon = (type: SummaryCardConfig['icon']) => {
  const iconMap = {
    api: <ApiOutlined />,
    clock: <ClockCircleOutlined />,
    database: <DatabaseOutlined />,
    node: <NodeIndexOutlined />,
    thunder: <ThunderboltOutlined />
  };
  return iconMap[type];
};

export default function SimpleDashboard({ config }: { config: SimpleDashboardConfig }) {
  const {
    displayMode,
    setDisplayMode,
    pageTitle,
    timeValues,
    timeDefaultValue,
    frequence,
    setFrequence,
    metricsRefreshSignal,
    currentInstanceInterval,
    monitorObjectId,
    monitorObjectName,
    instanceId,
    resolvedInstanceName,
    idValues,
    collectionStatus,
    collectionStatusTimeline,
    objectMetaItems,
    instanceSelectValue,
    instanceLoading,
    instanceSelectOptions,
    currentInstanceLabel,
    isDashboardMode,
    summaryCards,
    chartPanels,
    ringPanels,
    barPanels,
    detailPanels,
    onTimeChange,
    onRefresh,
    onXRangeChange,
    onBack,
    onInstanceChange
  } = useSimpleDashboardData(config);

  return (
    <div className={styles.page}>
      <div className={styles.shell}>
        <div className={styles.pageHeader}>
          <DashboardPageHeader
            title={pageTitle}
            displayMode={displayMode}
            onDisplayModeChange={setDisplayMode}
            timeDefaultValue={timeDefaultValue}
            onTimeChange={onTimeChange}
            onFrequenceChange={setFrequence}
            onRefresh={onRefresh}
            onBack={onBack}
            showTimeSelector={false}
            styles={styles}
          />
          <DashboardInstanceCard
            instanceName={resolvedInstanceName}
            metaItems={objectMetaItems.map((item, index) => <span key={index} className={styles.instanceMetaInline}>{item}</span>)}
            icon={<DatabaseOutlined />}
            selectorValue={instanceSelectValue}
            selectorLoading={instanceLoading}
            selectorOptions={instanceSelectOptions}
            onInstanceChange={onInstanceChange}
            selectorPlaceholder={resolvedInstanceName !== '--' ? resolvedInstanceName : '选择实例'}
            selectorTitle={currentInstanceLabel}
            isDashboardMode={isDashboardMode}
            timeSelectorProps={{
              timeDefaultValue,
              onTimeChange,
              onFrequenceChange: setFrequence,
              onRefresh
            }}
            styles={styles}
          />
        </div>

        <div>
          {displayMode === 'dashboard' ? (
            <>
              <div className={styles.primaryGrid}>
                <CollectionStatusCard
                  status={collectionStatus}
                  timeline={collectionStatusTimeline}
                  guideItems={[
                    { label: '采集状态', detail: `展示最近一段时间内该 ${config.objectFallbackName} 实例监控采集是否正常、缺失或异常。` },
                    { label: '状态时间线', detail: '绿色表示采集成功，灰色表示暂无数据，红色表示采集或查询异常。' }
                  ]}
                  styles={styles}
                />
                {summaryCards.map(({ card, mainValue, valueColor, compare, footerItems, trendData, noDataType, uptimeState }) => {
                  const isUptime = card.isUptimeCard && uptimeState;
                  return (
                    <StatCard
                      key={card.title}
                      title={<TitleWithGuide title={card.title} items={card.guide} styles={styles} />}
                      value={mainValue.value}
                      unit={mainValue.unit}
                      icon={getIcon(card.icon)}
                      iconStyle={{ background: `${valueColor ?? card.color}1f`, color: valueColor ?? card.color }}
                      color={valueColor ?? card.color}
                      className={isUptime ? styles.statCardRelaxed : undefined}
                      bodyClassName={isUptime ? styles.statBodyRelaxed : undefined}
                      footer={
                        <>
                          {footerItems.map((field) => (
                            <span key={field.label}>{field.label} {field.value}</span>
                          ))}
                        </>
                      }
                      compare={compare}
                      compareFavorableDirection={card.compareFavorableDirection}
                      trendData={isUptime ? [] : trendData}
                      hideTrend={isUptime ? true : card.hideTrend}
                      noDataType={noDataType}
                      styles={styles}
                      extra={isUptime ? (
                        <div className={`${styles.uptimeStatus} ${styles[`uptimeStatus${uptimeState.tone === 'success' ? 'Success' : uptimeState.tone === 'warning' ? 'Warning' : 'Empty'}`]}`}>
                          <span className={styles.uptimeStatusDot} />
                          <div className={styles.uptimeStatusMainWrap}>
                            <span className={styles.uptimeStatusMain}>{uptimeState.label}</span>
                          </div>
                        </div>
                      ) : undefined}
                    />
                  );
                })}
              </div>

              <div className={styles.chartGrid}>
                {chartPanels.map(({ chart, data, metric, unit, legends, seriesStyles }) => (
                  <TrendChartPanel
                    key={chart.title}
                    title={chart.title}
                    subtitle={chart.subtitle}
                    guide={chart.guide}
                    legends={legends}
                    data={data}
                    metric={metric}
                    unit={unit}
                    seriesStyles={seriesStyles}
                    onXRangeChange={onXRangeChange}
                    className={styles.panel}
                    styles={styles}
                  />
                ))}
              </div>

              {(ringPanels.length > 0 || barPanels.length > 0) ? (
                <div className={styles.insightGrid}>
                  {ringPanels.map(({ panel, data, centerValue, isEmpty }) => (
                    <RingChartPanel
                      key={panel.title}
                      title={panel.title}
                      subtitle={panel.subtitle}
                      guide={panel.guide}
                      data={data}
                      centerValue={centerValue}
                      centerCaption={panel.centerCaption}
                      isEmpty={isEmpty}
                      className={styles.panel}
                      styles={styles}
                    />
                  ))}
                  {barPanels.map(({ panel, items }) => (
                    <HorizontalBarPanel
                      key={panel.title}
                      title={panel.title}
                      subtitle={panel.subtitle}
                      guide={panel.guide}
                      items={items}
                      className={styles.panel}
                      styles={styles}
                    />
                  ))}
                </div>
              ) : null}

              <div className={styles.detailGrid}>
                {detailPanels.map(({ panel, rows, hasData }) => (
                  <div key={panel.title} className={styles.panel}>
                    <h3 className={styles.panelTitle}>{panel.title}</h3>
                    <div className={styles.panelSubTitle}>{panel.subtitle}</div>
                    {hasData ? rows.map((row) => (
                      <div key={row.label} className={styles.detailMetricRow}>
                        <span>{row.label}</span>
                        <span className={styles.detailMetricValue}>{row.value}</span>
                      </div>
                    )) : <div className={styles.detailEmpty}>当前时间范围内暂无可展示详情</div>}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className={styles.metricsMode}>
              <div className={`${styles.panel} ${styles.fullPanel}`}>
                <div className={styles.sectionHeading}>
                  <h3 className={styles.panelTitle}>
                    <TitleWithGuide title="监控指标全量" items={[{ label: '监控指标全景', detail: '承载完整原始监控视图，适合在仪表盘发现异常后继续下钻排查。' }]} styles={styles} />
                  </h3>
                </div>
                <MetricViews
                  monitorObjectId={monitorObjectId}
                  monitorObjectName={monitorObjectName}
                  instanceId={instanceId}
                  instanceName={resolvedInstanceName}
                  idValues={idValues}
                  externalTimeValues={timeValues}
                  externalTimeDefaultValue={timeDefaultValue}
                  externalFrequence={frequence}
                  externalRefreshSignal={metricsRefreshSignal}
                  collectionInterval={currentInstanceInterval}
                  hideTimeSelector
                  onExternalXRangeChange={onXRangeChange}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
