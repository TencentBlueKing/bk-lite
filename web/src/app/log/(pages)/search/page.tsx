'use client';
import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import TimeSelector from '@/components/time-selector';
import { ListItem, TimeSelectorDefaultValue, TimeSelectorRef } from '@/types';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  SearchOutlined,
  BulbFilled,
  StarOutlined,
  FolderOpenOutlined
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import {
  Card,
  Button,
  Select,
  Segmented,
  Spin,
  InputNumber,
  message
} from 'antd';
import { useTranslation } from '@/utils/i18n';
import searchStyle from './index.module.scss';
import Collapse from '@/components/collapse';
import CustomBarChart from '@/app/log/components/charts/barChart';
import GrammarExplanation from '@/components/operate-drawer';
import SearchTable from './searchTable';
import FieldList from './fieldList';
import LogTerminal from './logTerminal';
import LogQueryInput, {
  type LogQueryTimeRange
} from '@/app/log/components/log-query-input';
import {
  ChartData,
  ModalRef,
  Pagination,
  TableDataItem
} from '@/app/log/types';
import useApiClient from '@/utils/request';
import useSearchApi from '@/app/log/api/search';
import useIntegrationApi from '@/app/log/api/integration';
import useLogUserHabitApi, {
  LOG_SEARCH_HISTOGRAM_HABIT_KEY
} from '@/app/log/api/userHabit';
import { useHabitExpanded } from '@/hooks/useHabitExpanded';
import {
  SearchParams,
  LogTerminalRef,
  Conidtion,
  SearchConfig
} from '@/app/log/types/search';
import { aggregateLogs } from '@/app/log/utils/common';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import MarkdownRenderer from '@/components/markdown';
import AddConditions from './addConditions';
import { v4 as uuidv4 } from 'uuid';
import ConditionList from './conditionList';
import usePermissions from '@/hooks/usePermissions';
import { CollectTypeItem } from '@/app/log/types/integration';
import {
  buildInstanceExtractorPath,
  buildTypeExtractorPath,
  resolveExtractorCreateTarget,
  storeExtractorCreateSample
} from '@/app/log/(pages)/integration/receive/logExtractorLogic';

const { Option } = Select;
const PAGE_LIMIT = 100;
const DEFAULT_DISPLAY_FIELDS = ['timestamp', 'message'];

const getStoredDisplayFields = () => {
  if (typeof window === 'undefined') {
    return DEFAULT_DISPLAY_FIELDS;
  }

  const stored = localStorage.getItem('logSearchFields');
  if (!stored) {
    return DEFAULT_DISPLAY_FIELDS;
  }

  try {
    const parsed = JSON.parse(stored);
    if (!Array.isArray(parsed)) {
      return DEFAULT_DISPLAY_FIELDS;
    }

    const normalized = parsed.filter(
      (field): field is string =>
        typeof field === 'string' &&
        !!field &&
        !['@timestamp', '_stream', '_stream_id', '_time'].includes(field)
    );
    const result = [...normalized];
    DEFAULT_DISPLAY_FIELDS.forEach((field) => {
      if (!result.includes(field)) {
        result.unshift(field);
      }
    });
    return result;
  } catch {
    return DEFAULT_DISPLAY_FIELDS;
  }
};

const quoteLogsqlToken = (value: unknown) => {
  const normalized = String(value ?? '');
  const escaped = normalized
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r');
  return `"${escaped}"`;
};

const QUERY_CONNECTOR_REGEXP = /(\||\(|AND|OR)$/i;

const SearchView: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isLoading } = useApiClient();
  const { getLogStreams, getFields, getCollectTypes, getLogExtractors } =
    useIntegrationApi();
  const { hasPermission: hasConfigurePermission } = usePermissions(
    '/log/integration/list/detail/configure'
  );
  const { getHits, getLogs } = useSearchApi();
  const { getUserHabit, saveUserHabit } = useLogUserHabitApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const queryText = searchParams.get('query') || '';
  const startTime = searchParams.get('startTime') || '';
  const endTime = searchParams.get('endTime') || '';
  const urlLogGroups = searchParams.getAll('log_groups');
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const terminalRef = useRef<LogTerminalRef | null>(null);
  const timeSelectorRef = useRef<TimeSelectorRef>(null);
  const conditionRef = useRef<ModalRef>(null);
  const conditionListRef = useRef<ModalRef>(null);
  const searchTextRef = useRef<string>(queryText);
  const [hasSearchText, setHasSearchText] = useState<boolean>(!!queryText);
  const [frequence, setFrequence] = useState<number>(0);
  const [defaultSearchText, setDefaultSearchText] = useState<string>(queryText);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [queryTime, setQueryTime] = useState<Date>(new Date());
  const [queryEndTime, setQueryEndTime] = useState<Date>(new Date());
  const [groupList, setGroupList] = useState<ListItem[]>([]);
  const [fields, setFields] = useState<string[]>([]);
  const [columnFields, setColumnFields] = useState<string[]>(() =>
    getStoredDisplayFields()
  );
  const [groups, setGroups] = useState<React.Key[]>([]);
  const [pagination, setPagination] = useState<Pagination>({
    current: 0,
    total: 0,
    pageSize: PAGE_LIMIT
  });
  const loadHistogramHabit = useCallback(
    () => getUserHabit(LOG_SEARCH_HISTOGRAM_HABIT_KEY),
    [getUserHabit]
  );
  const saveHistogramHabit = useCallback(
    (value: { expanded: boolean }) =>
      saveUserHabit(LOG_SEARCH_HISTOGRAM_HABIT_KEY, value),
    [saveUserHabit]
  );
  const [expand, setExpand] = useHabitExpanded({
    enabled: !isLoading,
    load: loadHistogramHabit,
    save: saveHistogramHabit
  });
  const [chartData, setChartData] = useState<ChartData[]>([]);
  const [visible, setVisible] = useState<boolean>(false);
  const [activeMenu, setActiveMenu] = useState<string>('list');
  const [pageLoading, setPageLoading] = useState<boolean>(false);
  const [chartLoading, setChartLoading] = useState<boolean>(false);
  const [treeLoading, setTreeLoading] = useState<boolean>(false);
  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [terminalLoading, setTerminalLoading] = useState<boolean>(false);
  const [timeDefaultValue, setTimeDefaultValue] =
    useState<TimeSelectorDefaultValue>({
      selectValue: startTime ? 0 : 15,
      rangePickerVaule: endTime ? [dayjs(+startTime), dayjs(+endTime)] : null
    });
  const [windowHeight, setWindowHeight] = useState<number>(window.innerHeight);
  const [limit, setLimit] = useState<number | null>(100);
  const suggestionTimeRange = useMemo<LogQueryTimeRange>(() => {
    if (timeDefaultValue.selectValue) {
      return {
        mode: 'relative',
        minutes: timeDefaultValue.selectValue
      };
    }
    const [start, end] = timeDefaultValue.rangePickerVaule || [];
    if (start && end) {
      return {
        mode: 'absolute',
        start: start.valueOf(),
        end: end.valueOf()
      };
    }
    return { mode: 'relative', minutes: 15 };
  }, [timeDefaultValue]);

  const isList = useMemo(() => activeMenu === 'list', [activeMenu]);

  const scrollHeight = useMemo(() => {
    // 根据expand状态和屏幕高度动态计算scroll高度
    const fixedHeight = expand ? 490 : 410;
    return Math.max(200, windowHeight - fixedHeight);
  }, [windowHeight, expand]);

  const disableStore = useMemo(
    () => !groups.length || !searchTextRef.current,
    [groups, hasSearchText]
  );

  useEffect(() => {
    if (isLoading) return;
    getAllFields();
    initData();
  }, [isLoading]);

  useEffect(() => {
    localStorage.setItem('logSearchFields', JSON.stringify(columnFields));
  }, [columnFields]);

  useEffect(() => {
    if (!frequence) {
      clearTimer();
      return;
    }
    timerRef.current = setInterval(() => {
      getLogData('timer');
    }, frequence);
    return () => {
      clearTimer();
    };
  }, [frequence, groups, limit]);

  useEffect(() => {
    const handleResize = () => {
      setWindowHeight(window.innerHeight);
    };
    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  const onTabChange = async (val: string) => {
    setActiveMenu(val);
    setChartData([]);
    setTableData([]);
    if (val === 'list') {
      onRefresh();
    }
  };

  const initData = async () => {
    try {
      setPageLoading(true);
      const data = await getLogStreams({
        page_size: -1,
        page: 1
      });
      const list = data || [];
      const availableIds = list
        .map((item) => item.id)
        .filter((id): id is React.Key => !!id);
      const selectedIds = urlLogGroups.length
        ? availableIds.filter((id) => urlLogGroups.includes(String(id)))
        : list.at()?.id
          ? [list.at().id]
          : [];
      setGroupList(list);
      setGroups(selectedIds);
      if (list.length) {
        await getAllFieldsByConfig({ logGroups: selectedIds });
        getLogData('init', { logGroups: selectedIds });
      }
    } finally {
      setPageLoading(false);
    }
  };

  const getAllFields = async () => {
    setTreeLoading(true);
    try {
      const { query, start_time, end_time, log_groups } = getSearchParams();
      const data = await getFields({
        query,
        start_time,
        end_time,
        log_groups
      });
      setFields(data || []);
    } finally {
      setTreeLoading(false);
    }
  };

  const getChartData = async (type: string, extra?: SearchConfig) => {
    setChartLoading(type !== 'timer');
    try {
      const params = getParams(extra);
      const res = await getHits(params);
      const chartData = aggregateLogs(res?.hits);
      const total = chartData.reduce((pre, cur) => (pre += cur.value), 0);
      setPagination((pre) => ({
        ...pre,
        total: total,
        current: 1
      }));
      setChartData(chartData);
    } finally {
      setChartLoading(false);
    }
  };

  const getTableData = async (type: string, extra?: SearchConfig) => {
    setTableLoading(type !== 'timer');
    try {
      const params = getParams(extra);
      const res = await getLogs(params);
      const listData: TableDataItem[] = (res || []).map(
        (item: TableDataItem) => ({
          ...item,
          id: uuidv4()
        })
      );
      setTableData(listData);
    } finally {
      setTableLoading(false);
    }
  };

  const getLogData = async (type: string, extra?: SearchConfig) => {
    if (!extra?.logGroups?.length && !groups.length) {
      return message.error(t('log.search.searchError'));
    }
    setTableData([]);
    setChartData([]);
    setQueryTime(new Date());
    setQueryEndTime(new Date());
    Promise.all([getChartData(type, extra), getTableData(type, extra)]).finally(
      () => {
        setQueryEndTime(new Date());
      }
    );
  };

  const getParams = (extra?: SearchConfig) => {
    const times = extra?.times || timeSelectorRef.current?.getValue() || [];
    const params: SearchParams = {
      start_time: times[0] ? new Date(times[0]).toISOString() : '',
      end_time: times[1] ? new Date(times[1]).toISOString() : '',
      field: '_stream',
      fields_limit: 5,
      log_groups: extra?.logGroups || groups,
      query: extra?.text || searchTextRef.current || '*',
      limit
    };
    params.step = Math.round((times[1] - times[0]) / 100) + 'ms';
    return params;
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const onRefresh = () => {
    getAllFields();
    getLogData('refresh');
  };

  const handleSearch = () => {
    if (isList) {
      onRefresh();
      return;
    }
    terminalRef?.current?.startLogStream();
  };

  const addToQuery = (row: TableDataItem, type: string) => {
    const currentText = searchTextRef.current;
    const trimmedText = currentText.trim();
    if (type === 'field') {
      const fieldName = String(row.label || '');
      const encodedField = /^[A-Za-z_][A-Za-z0-9_.]*$/.test(fieldName)
        ? fieldName
        : quoteLogsqlToken(fieldName);
      const fieldLabel = `${encodedField}:`;
      if (!trimmedText) {
        searchTextRef.current = fieldLabel;
      } else if (QUERY_CONNECTOR_REGEXP.test(trimmedText)) {
        searchTextRef.current = `${trimmedText} ${fieldLabel}`;
      } else {
        searchTextRef.current = `${trimmedText} AND ${fieldLabel}`;
      }
    } else {
      const fieldLabel = quoteLogsqlToken(row.label);
      const fieldValue = quoteLogsqlToken(row.value);
      const fieldExpression = `${fieldLabel}:${fieldValue}`;
      if (!trimmedText) {
        searchTextRef.current = fieldExpression;
      } else if (QUERY_CONNECTOR_REGEXP.test(trimmedText)) {
        searchTextRef.current = `${trimmedText} ${fieldExpression}`;
      } else {
        searchTextRef.current = `${trimmedText} AND ${fieldExpression}`;
      }
    }
    setDefaultSearchText(searchTextRef.current);
    setHasSearchText(!!searchTextRef.current);
  };

  const createExtractorFromLog = async (record: TableDataItem) => {
    const target = resolveExtractorCreateTarget({
      collect_type: record.collect_type,
      instance_id: record.instance_id
    });
    if (target.kind === 'unavailable') {
      message.error(t('log.extractor.missingInstance'));
      return;
    }
    if (target.kind === 'type') {
      if (!hasConfigurePermission(['Add'])) {
        message.error(t('common.noAuth'));
        return;
      }
      try {
        const types = await getCollectTypes();
        const list: CollectTypeItem[] = Array.isArray(types) ? types : [];
        const meta = list.find((item) => item.name === target.collectType);
        if (!meta) {
          message.error(t('log.extractor.unsupportedCollectType'));
          return;
        }
        storeExtractorCreateSample(
          { ...record },
          { kind: 'type', id: target.collectType }
        );
        router.push(buildTypeExtractorPath(meta, { create: true }));
      } catch {
        message.error(t('log.extractor.unsupportedCollectType'));
      }
      return;
    }
    try {
      const list = await getLogExtractors({
        collect_instance: target.instanceId
      });
      if (list.can_operate !== true) {
        message.error(t('log.extractor.instanceUnavailable'));
        return;
      }
    } catch {
      message.error(t('log.extractor.instanceUnavailable'));
      return;
    }
    storeExtractorCreateSample(
      { ...record },
      { kind: 'instance', id: target.instanceId }
    );
    router.push(buildInstanceExtractorPath(target.instanceId, { create: true }));
  };

  const onXRangeChange = (arr: [Dayjs, Dayjs]) => {
    setTimeDefaultValue((pre) => ({
      ...pre,
      rangePickerVaule: arr,
      selectValue: 0
    }));
    const times = arr.map((item) => dayjs(item).valueOf());
    getAllFieldsByConfig({ times });
    getLogData('refresh', { times });
  };

  const onTimeChange = (range: number[], originValue: number | null) => {
    setTimeDefaultValue({
      selectValue: originValue || 0,
      rangePickerVaule: originValue ? null : [dayjs(range[0]), dayjs(range[1])]
    });
    onRefresh();
  };

  const openConditonsModal = (type: string) => {
    const { query, start_time, end_time, log_groups } = getParams();
    conditionRef.current?.showModal({
      title: t('log.search.storageConditions'),
      type,
      form: {
        query,
        log_groups,
        time_range: {
          origin_value: timeDefaultValue.selectValue,
          start: start_time,
          end: end_time
        }
      }
    });
  };

  const loadConditions = (row = {}, type: string) => {
    conditionListRef.current?.showModal({
      title: t('log.search.loadConditions'),
      type,
      form: row
    });
  };

  const handleConditionSearch = (condition: Conidtion) => {
    const { log_groups, query, time_range } = condition;
    const start = +new Date(time_range.start);
    const end = +new Date(time_range.end);
    setGroups(log_groups);
    searchTextRef.current = query;
    setHasSearchText(!!query);
    setDefaultSearchText(query);
    setTimeDefaultValue({
      selectValue: (time_range.origin_value as number) || 0,
      rangePickerVaule: time_range.origin_value
        ? null
        : [dayjs(start), dayjs(end)]
    });
    getAllFieldsByConfig({
      logGroups: log_groups,
      text: query,
      times: [start, end]
    });
    getLogData('refresh', {
      logGroups: log_groups,
      text: query,
      times: [start, end]
    });
  };

  const getAllFieldsByConfig = async (extra?: SearchConfig) => {
    setTreeLoading(true);
    try {
      const params = getParams(extra);
      const data = await getFields({
        query: params.query,
        start_time: params.start_time,
        end_time: params.end_time,
        log_groups: params.log_groups
      });
      setFields(data || []);
    } finally {
      setTreeLoading(false);
    }
  };

  // 获取搜索参数的方法（用于字段Top值统计）
  const getSearchParams = () => {
    const times = timeSelectorRef.current?.getValue() || [];
    return {
      query: searchTextRef.current || '*',
      start_time: times[0] ? new Date(times[0]).toISOString() : '',
      end_time: times[1] ? new Date(times[1]).toISOString() : '',
      log_groups: groups
    };
  };

  return (
    <div className={`${searchStyle.search} w-full`}>
      <Spin spinning={pageLoading}>
        <Card bordered={false} className={searchStyle.searchCondition}>
          <b className="flex mb-[10px]">{t('log.search.searchCriteria')}</b>
          <div className="flex">
            <Select
              style={{
                width: '250px'
              }}
              showSearch
              mode="multiple"
              maxTagCount="responsive"
              placeholder={t('log.search.selectGroup')}
              value={groups}
              onChange={(val) => setGroups(val)}
            >
              {groupList.map((item) => (
                <Option value={item.id} key={item.id}>
                  {item.name}
                </Option>
              ))}
            </Select>
            <LogQueryInput
              className="flex-1 mx-[8px]"
              placeholder={t('log.search.searchPlaceHolder')}
              value={defaultSearchText}
              availableFields={fields}
              logGroups={groups}
              timeRange={suggestionTimeRange}
              fieldsLoading={treeLoading}
              addonAfter={
                <BulbFilled
                  className="cursor-pointer px-[10px] py-[8px]"
                  style={{ color: 'var(--color-primary)' }}
                  onClick={() => setVisible(true)}
                />
              }
              onChange={(value) => {
                searchTextRef.current = value;
                setDefaultSearchText(value);
                setHasSearchText(!!value);
              }}
              onPressEnter={handleSearch}
            />
            <Button
              className="mr-[8px]"
              icon={<StarOutlined />}
              disabled={disableStore}
              title={t('log.search.storageConditions')}
              onClick={() => openConditonsModal('add')}
            />
            <Button
              className="mr-[8px]"
              icon={<FolderOpenOutlined />}
              title={t('log.search.loadConditions')}
              onClick={() => loadConditions({}, 'add')}
            />
            <Button
              type="primary"
              icon={<SearchOutlined />}
              onClick={handleSearch}
            >
              {t('log.search.search')}
            </Button>
          </div>
        </Card>
        <div className="my-[10px] flex items-center justify-between">
          <Segmented
            value={activeMenu}
            options={[
              { value: 'list', label: t('log.search.list') },
              { value: 'overview', label: t('log.search.terminal') }
            ]}
            onChange={onTabChange}
          />
          <div className={isList ? 'flex items-center' : 'hidden'}>
            <span className="text-[var(--color-text-3)] text-[12px] mr-[8px]">
              {t('log.search.listTotal')}
            </span>
            <div className="flex">
              <InputNumber
                className="mr-[8px] w-[100px]"
                placeholder={t('common.inputMsg')}
                value={limit}
                min={1}
                max={1000}
                precision={0}
                controls={false}
                onChange={(val) => setLimit(val || 1)}
              />
            </div>
            <TimeSelector
              ref={timeSelectorRef}
              defaultValue={timeDefaultValue}
              onChange={onTimeChange}
              onFrequenceChange={onFrequenceChange}
              onRefresh={onRefresh}
            />
          </div>
        </div>
        {isList ? (
          <>
            <Spin spinning={chartLoading}>
              <Card bordered={false} className="mb-[10px]">
                <Collapse
                  title={t('log.search.histogram')}
                  icon={
                    <div>
                      <span className="mr-2">
                        <span className="text-[var(--color-text-3)]">
                          {t('log.search.total')}：
                        </span>
                        <span>{pagination.total}</span>
                      </span>
                      <span className="mr-2">
                        <span className="text-[var(--color-text-3)]">
                          {t('log.search.queryTime')}：
                        </span>
                        <span>{convertToLocalizedTime(String(queryTime))}</span>
                      </span>
                      <span className="mr-2">
                        <span className="text-[var(--color-text-3)]">
                          {t('log.search.timeConsumption')}：
                        </span>
                        <span>{`${
                          Number(queryEndTime) - Number(queryTime)
                        }ms`}</span>
                      </span>
                    </div>
                  }
                  isOpen={expand}
                  onToggle={(val) => setExpand(val)}
                >
                  <CustomBarChart
                    className={searchStyle.chart}
                    data={chartData}
                    onXRangeChange={onXRangeChange}
                  />
                </Collapse>
              </Card>
            </Spin>
            <Card
              bordered={false}
              style={{
                minHeight: scrollHeight + 74 + 'px',
                overflowY: 'hidden'
              }}
            >
              <div className={searchStyle.tableArea}>
                <Spin spinning={treeLoading}>
                  <FieldList
                    style={{ height: scrollHeight + 'px' }}
                    className="w-[230px] min-w-[230px] flex-shrink-0"
                    fields={fields}
                    displayFields={columnFields}
                    addToQuery={addToQuery}
                    changeDisplayColumns={(val) => {
                      setColumnFields(val);
                    }}
                    getSearchParams={getSearchParams}
                  />
                </Spin>
                <SearchTable
                  loading={tableLoading}
                  dataSource={tableData}
                  fields={columnFields}
                  scroll={{ x: 'calc(100vw-350px)', y: scrollHeight }}
                  addToQuery={addToQuery}
                  onCreateExtractor={(row) => {
                    void createExtractorFromLog(row);
                  }}
                />
              </div>
            </Card>
          </>
        ) : (
          <Spin spinning={terminalLoading}>
            <LogTerminal
              ref={terminalRef}
              className="h-[calc(100vh-244px)]"
              query={getParams()}
              fetchData={(val) => setTerminalLoading(val)}
            />
          </Spin>
        )}
      </Spin>
      <GrammarExplanation
        title={t('log.search.grammarExplanation')}
        visible={visible}
        width={600}
        onClose={() => setVisible(false)}
        footer={
          <Button onClick={() => setVisible(false)}>
            {t('common.cancel')}
          </Button>
        }
      >
        <MarkdownRenderer filePath="grammar_explanation" fileName="index" />
      </GrammarExplanation>
      <AddConditions ref={conditionRef} />
      <ConditionList ref={conditionListRef} onSuccess={handleConditionSearch} />
    </div>
  );
};

export default SearchView;
