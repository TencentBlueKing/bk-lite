'use client';
import React, { useState, useRef, useEffect, useMemo } from 'react';
import TimeSelector from '@/components/time-selector';
import { ListItem, TimeSelectorDefaultValue, TimeSelectorRef } from '@/types';
import { useSearchParams } from 'next/navigation';
import {
  SearchOutlined,
  BulbFilled,
  StarOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import {
  Card,
  Button,
  Select,
  Segmented,
  Spin,
  InputNumber,
  message,
} from 'antd';
import { useTranslation } from '@/utils/i18n';
import searchStyle from './index.module.scss';
import Collapse from '@/components/collapse';
import CustomBarChart from '@/app/log/components/charts/barChart';
import GrammarExplanation from '@/app/log/components/operate-drawer';
import SearchTable from './searchTable';
import FieldList from './fieldList';
import LogTerminal from './logTerminal';
import SearchInput from './smartSearchInput';
import {
  ChartData,
  ModalRef,
  Pagination,
  TableDataItem,
} from '@/app/log/types';
import useApiClient from '@/utils/request';
import useSearchApi from '@/app/log/api/search';
import useIntegrationApi from '@/app/log/api/integration';
import {
  SearchParams,
  LogTerminalRef,
  Conidtion,
  SearchConfig,
} from '@/app/log/types/search';
import { aggregateLogs } from '@/app/log/utils/common';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import MarkdownRenderer from '@/components/markdown';
import AddConditions from './addConditions';
import { v4 as uuidv4 } from 'uuid';
import ConditionList from './conditionList';

const { Option } = Select;
const PAGE_LIMIT = 100;

const SearchView: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const { isLoading } = useApiClient();
  const { getLogStreams, getFields } = useIntegrationApi();
  const { getHits, getLogs } = useSearchApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const terminalRef = useRef<LogTerminalRef | null>(null);
  const timeSelectorRef = useRef<TimeSelectorRef>(null);
  const conditionRef = useRef<ModalRef>(null);
  const conditionListRef = useRef<ModalRef>(null);
  const [frequence, setFrequence] = useState<number>(0);
  const queryText = searchParams.get('query') || '';
  const startTime = searchParams.get('startTime') || '';
  const endTime = searchParams.get('endTime') || '';
  const [searchText, setSearchText] = useState<string>(queryText);
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [queryTime, setQueryTime] = useState<Date>(new Date());
  const [queryEndTime, setQueryEndTime] = useState<Date>(new Date());
  const [groupList, setGroupList] = useState<ListItem[]>([]);
  const [fields, setFields] = useState<string[]>([]);
  const [columnFields, setColumnFields] = useState<string[]>([]);
  const [groups, setGroups] = useState<React.Key[]>([]);
  const [pagination, setPagination] = useState<Pagination>({
    current: 0,
    total: 0,
    pageSize: PAGE_LIMIT,
  });
  const [expand, setExpand] = useState<boolean>(true);
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
      rangePickerVaule: endTime ? [dayjs(+startTime), dayjs(+endTime)] : null,
    });
  const [windowHeight, setWindowHeight] = useState<number>(window.innerHeight);
  const [limit, setLimit] = useState<number | null>(100);

  const isList = useMemo(() => activeMenu === 'list', [activeMenu]);

  const scrollHeight = useMemo(() => {
    // 根据expand状态和屏幕高度动态计算scroll高度
    const fixedHeight = expand ? 480 : 400;
    return Math.max(200, windowHeight - fixedHeight);
  }, [windowHeight, expand]);

  const disableStore = useMemo(
    () => !groups.length || !searchText,
    [groups, searchText]
  );

  useEffect(() => {
    if (isLoading) return;
    getAllFields();
    initData();
  }, [isLoading]);

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
  }, [frequence, searchText, groups, limit]);

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
        page: 1,
      });
      const list = data || [];
      const ids = list.at()?.id ? [list.at().id] : [];
      setGroupList(list);
      setGroups(ids);
      if (list.length) {
        getLogData('init', { logGroups: ids });
      }
    } finally {
      setPageLoading(false);
    }
  };

  const getAllFields = async () => {
    setTreeLoading(true);
    try {
      const data = await getFields();
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
        current: 1,
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
          id: uuidv4(),
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
      query: extra?.text || searchText || '*',
      limit,
    };
    params.step = Math.round((times[1] - times[0]) / 100) + 'ms';
    return params;
  };

  const onFrequenceChange = (val: number) => {
    setFrequence(val);
  };

  const onRefresh = () => {
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
    setSearchText((pre: string) => {
      if (type === 'field') {
        const pattern = /fields/;
        if (pre.match(pattern)) {
          return pre.replace(pattern, `fields ${row.label},`);
        }
        return pre ? `${pre} | fields ${row.label}` : `fields ${row.label}`;
      }
      return pre
        ? `${row.label}:${row.value} | ${pre}`
        : `${row.label}:${row.value}`;
    });
  };

  const onXRangeChange = (arr: [Dayjs, Dayjs]) => {
    setTimeDefaultValue((pre) => ({
      ...pre,
      rangePickerVaule: arr,
      selectValue: 0,
    }));
    const times = arr.map((item) => dayjs(item).valueOf());
    getLogData('refresh', { times });
  };

  const onTimeChange = (range: number[], originValue: number | null) => {
    setTimeDefaultValue({
      selectValue: originValue || 0,
      rangePickerVaule: originValue ? null : [dayjs(range[0]), dayjs(range[1])],
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
          end: end_time,
        },
      },
    });
  };

  const loadConditions = (row = {}, type: string) => {
    conditionListRef.current?.showModal({
      title: t('log.search.loadConditions'),
      type,
      form: row,
    });
  };

  const handleConditionSearch = (condition: Conidtion) => {
    const { log_groups, query, time_range } = condition;
    const start = +new Date(time_range.start);
    const end = +new Date(time_range.end);
    setGroups(log_groups);
    setSearchText(query);
    setTimeDefaultValue({
      selectValue: (time_range.origin_value as number) || 0,
      rangePickerVaule: time_range.origin_value
        ? null
        : [dayjs(start), dayjs(end)],
    });
    getLogData('refresh', {
      logGroups: log_groups,
      text: query,
      times: [start, end],
    });
  };

  // 获取时间范围的方法
  const getTimeRange = () => {
    return timeSelectorRef.current?.getValue() || [];
  };

  return (
    <div className={`${searchStyle.search} w-full`}>
      <Spin spinning={pageLoading}>
        <Card bordered={false} className={searchStyle.searchCondition}>
          <b className="flex mb-[10px]">{t('log.search.searchCriteria')}</b>
          <div className="flex">
            <Select
              style={{
                width: '250px',
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
            <SearchInput
              className="flex-1 mx-[8px]"
              placeholder={t('log.search.searchPlaceHolder')}
              value={searchText}
              fields={fields}
              getTimeRange={getTimeRange}
              addonAfter={
                <BulbFilled
                  className="cursor-pointer px-[10px] py-[8px]"
                  style={{ color: 'var(--color-primary)' }}
                  onClick={() => setVisible(true)}
                />
              }
              onChange={setSearchText}
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
              { value: 'overview', label: t('log.search.terminal') },
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
                max={1000000}
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
                overflowY: 'hidden',
              }}
            >
              <div className={searchStyle.tableArea}>
                <Spin spinning={treeLoading}>
                  <FieldList
                    style={{ height: scrollHeight + 'px' }}
                    className="w-[180px] min-w-[180px]"
                    fields={fields}
                    addToQuery={addToQuery}
                    changeDisplayColumns={(val) => {
                      setColumnFields(val);
                    }}
                  />
                </Spin>
                <SearchTable
                  loading={tableLoading}
                  dataSource={tableData}
                  fields={columnFields}
                  scroll={{ x: 'calc(100vw-300px)', y: scrollHeight }}
                  addToQuery={addToQuery}
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
