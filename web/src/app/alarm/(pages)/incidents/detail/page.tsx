'use client';

import React, { useState, useEffect } from 'react';
import Icon from '@/components/icon';
import CustomBreadcrumb from '@/app/alarm/components/customBreadcrumb';
import styles from './page.module.scss';
import AlarmTable from '@/app/alarm/(pages)/alarms/components/alarmTable';
import GanttChart from '../components/ganttChart';
import LinkModal from '../components/linkModal';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import AlarmAction from '@/app/alarm/(pages)/alarms/components/alarmAction';
import SearchFilter from '@/app/alarm/components/searchFilter';
import PermissionWrapper from '@/components/permission';
import { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import { useAlarmApi } from '@/app/alarm/api/alarms';
import { UserItem } from '@/app/alarm/types/types';
import { useCommon } from '@/app/alarm/context/common';
import { useTranslation } from '@/utils/i18n';
import { useSearchParams } from 'next/navigation';
import { useIncidentsApi } from '@/app/alarm/api/incidents';
import { message, Spin, Modal, Timeline, Empty } from 'antd';
import { IncidentTableDataItem } from '@/app/alarm/types/incidents';
import { useStateMap } from '@/app/alarm/constants/alarm';
import {
  EditOutlined,
  CheckOutlined,
  CloseOutlined,
  AppstoreOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import {
  Breadcrumb,
  Descriptions,
  Tabs,
  Input,
  Button,
  Segmented,
  Select,
  Tag,
} from 'antd';
import { useSettingApi } from '@/app/alarm/api/settings';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { TimeLineItem } from '@/app/alarm/types/types';

const { TabPane } = Tabs;

const IncidentDetail: React.FC = () => {
  const { t } = useTranslation();
  const { getLogList } = useSettingApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [timeLineData, setTimeLineData] = useState<TimeLineItem[]>([]);
  const [recordLoading, setRecordLoading] = useState<boolean>(false);
  const { levelListIncident, levelMapIncident, userList } = useCommon();
  const { getAlarmList } = useAlarmApi();
  const { getIncidentDetail, modifyIncidentDetail } = useIncidentsApi();
  const STATE_MAP = useStateMap();
  const searchParams = useSearchParams();
  const rowDetailId = searchParams.get('id') || '';
  const incidentId = searchParams.get('incident_id') || '';
  const [tableData, setTableData] = useState<AlarmTableDataItem[]>([]);
  const [tabLoading, setTabLoading] = useState<boolean>(false);
  const [viewType, setViewType] = useState<'table' | 'gantt'>('table');
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [operateVisible, setOperateVisible] = useState(false);
  const [editingAssignee, setEditingAssignee] = useState(false);
  const [selectedAssignees, setSelectedAssignees] = useState<string[]>([]);
  const [preAssignees, setPreAssignees] = useState<string[]>([]);
  const [assigneeDisplay, setAssigneeDisplay] = useState<string>('');
  const [incidentDetail, setIncidentDetail] = useState<IncidentTableDataItem>();
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [assigneeLoading, setAssigneeLoading] = useState(false);
  const [unlinkLoading, setUnlinkLoading] = useState(false);
  const [rowUnlinkKey, setRowUnlinkKey] = useState<React.Key | null>(null);
  const [linkingLoading, setLinkingLoading] = useState(false);
  const [editingNote, setEditingNote] = useState(false);
  const [noteValue, setNoteValue] = useState('');
  const [preNote, setPreNote] = useState('');
  const [noteLoading, setNoteLoading] = useState(false);

  const alarmAttrList = [
    {
      attr_id: 'alert_id',
      attr_name: t('alarms.alertId'),
      attr_type: 'str',
      option: [],
    },
    {
      attr_id: 'title',
      attr_name: t('alarms.alertName'),
      attr_type: 'str',
      option: [],
    },
    {
      attr_id: 'content',
      attr_name: t('alarms.alertContent'),
      attr_type: 'str',
      option: [],
    },
  ];

  useEffect(() => {
    fetchAlarmList();
    fetchIncidentDetail();
    fetchTimeline();
  }, [rowDetailId]);

  const fetchIncidentDetail = async () => {
    setLoadingDetail(true);
    try {
      const res = await getIncidentDetail(rowDetailId);
      setIncidentDetail(res);
    } finally {
      setLoadingDetail(false);
    }
  };

  const fetchAlarmList = async (
    titleSearch?: string,
    condition?: { field: string; value: string }
  ) => {
    setTabLoading(true);
    try {
      const params: any = {
        page: 1,
        page_size: 10000,
        incident_id: rowDetailId,
        has_incident: '',
      };
      if (condition) {
        params[condition.field] = condition.value;
      } else {
        params.title = titleSearch === undefined ? '' : titleSearch;
      }
      const res = await getAlarmList(params);
      setTableData(res.items || []);
    } finally {
      setTabLoading(false);
    }
  };

  const userOptions = userList.map((u: UserItem) => ({
    label: `${u.display_name} (${u.username})`,
    value: u.username,
  }));

  useEffect(() => {
    if (incidentDetail?.operator_users) {
      const trimmedUsers = incidentDetail.operator_users
        .split(',')
        .map((user) => user.trim());
      setSelectedAssignees(trimmedUsers);
      setPreAssignees(trimmedUsers);
      setAssigneeDisplay(incidentDetail?.operator_users);
    }
  }, [incidentDetail?.operator_users]);

  useEffect(() => {
    if (incidentDetail) {
      setNoteValue(incidentDetail.note || '');
      setPreNote(incidentDetail.note || '');
    }
  }, [incidentDetail?.note]);

  const confirmAssignee = async () => {
    setAssigneeLoading(true);
    try {
      await modifyIncidentDetail(rowDetailId, { operator: selectedAssignees });
      message.success(t('common.saveSuccess'));
      setPreAssignees(selectedAssignees);
      setAssigneeDisplay(selectedAssignees.join(','));
      setEditingAssignee(false);
      fetchTimeline();
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setAssigneeLoading(false);
    }
  };
  const cancelAssignee = () => {
    setSelectedAssignees(preAssignees);
    setEditingAssignee(false);
  };

  const confirmNote = async () => {
    setNoteLoading(true);
    try {
      await modifyIncidentDetail(rowDetailId, { note: noteValue });
      message.success(t('common.saveSuccess'));
      setPreNote(noteValue);
      setEditingNote(false);
      fetchTimeline();
    } catch {
      message.error(t('common.saveFailed'));
    } finally {
      setNoteLoading(false);
    }
  };
  const cancelNote = () => {
    setNoteValue(preNote);
    setEditingNote(false);
  };

  const onTabTableChange = () => {
    fetchAlarmList();
  };

  const handleUnlink = (keys?: React.Key[]) => {
    Modal.confirm({
      title: t('alarmCommon.unlinkAlert'),
      content: `${t('common.confirm')}${t('alarmCommon.unlinkAlert')}`,
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        const isRow = !!keys;
        if (isRow) setRowUnlinkKey(keys![0]);
        else setUnlinkLoading(true);

        try {
          const toRemove = keys ?? selectedRowKeys;
          if (!toRemove.length) return;
          const remainingIds = tableData
            .map((i) => i.id)
            .filter((id) => !toRemove.includes(id));
          await modifyIncidentDetail(rowDetailId, { alert: remainingIds });
          message.success(
            t('alarmCommon.unlinkAlert') + t('alarmCommon.success')
          );
          if (!isRow) setSelectedRowKeys([]);
          fetchAlarmList();
          fetchTimeline();
        } catch {
          console.error(t('common.unlinkFailed'));
        } finally {
          if (isRow) setRowUnlinkKey(null);
          else setUnlinkLoading(false);
        }
      },
    });
  };

  const handleLink = () => {
    setOperateVisible(true);
  };

  const handleLinkConfirm = async (selectedKeys: React.Key[]) => {
    setLinkingLoading(true);
    try {
      const existingIds = tableData.map((i) => i.id);
      const newIds = Array.from(
        new Set([...existingIds, ...(selectedKeys as number[])])
      );
      await modifyIncidentDetail(rowDetailId, { alert: newIds });
      message.success(t('alarmCommon.linkAlert') + t('alarmCommon.success'));
      setOperateVisible(false);
      fetchAlarmList();
      fetchTimeline();
    } catch {
      console.error(t('common.linkFailed'));
    } finally {
      setLinkingLoading(false);
    }
  };

  const onRefresh = () => {
    fetchIncidentDetail();
    fetchAlarmList();
    fetchTimeline();
  };

  const fetchTimeline = async () => {
    if (!incidentId) return;
    setRecordLoading(true);
    try {
      const res: any = await getLogList({
        target_id: incidentId,
        page_size: 10000,
        page: 1,
      });
      const list = (res.items || []).map((item: any) => ({
        color: 'blue',
        children: (
          <div className="flex px-4 text-sm">
            <span className="w-[160px]">
              {item.created_at ? convertToLocalizedTime(item.created_at) : '--'}
            </span>
            <span className="w-[160px]">{item.operator_object || '--'}</span>
            <span className="w-[120px]">{item.operator || '--'}</span>
            <span className="flex-1">{item.overview || '--'}</span>
          </div>
        ),
      }));
      const header = {
        color: 'blue',
        children: (
          <div className="flex px-4 text-sm font-semibold">
            <span className="w-[160px]">{t('alarmCommon.time')}</span>
            <span className="w-[160px]">{t('alarmCommon.action')}</span>
            <span className="w-[120px]">{t('alarmCommon.operator')}</span>
            <span className="flex-1">{t('settings.operationLog.summary')}</span>
          </div>
        ),
      };
      setTimeLineData([header, ...list]);
    } finally {
      setRecordLoading(false);
    }
  };

  const renderDescItems = () =>
    descFields.map(({ label, key }, idx) => {
      if (key === 'status') {
        return (
          <Descriptions.Item label={label} key={idx}>
            <div className={`${styles.descContent} flex items-start`}>
              <span className="mr-4">
                {STATE_MAP[incidentDetail?.[key] as keyof typeof STATE_MAP] ||
                  '--'}
              </span>
              <AlarmAction
                from="incident"
                btnSize="small"
                displayMode="dropdown"
                rowData={[incidentDetail || ({} as IncidentTableDataItem)]}
                onAction={async () => {
                  fetchIncidentDetail();
                  fetchTimeline();
                }}
              />
            </div>
          </Descriptions.Item>
        );
      }
      if (key === 'operator_users') {
        return (
          <Descriptions.Item label={label} key={idx}>
            <div
              className={
                styles.descContent + ' flex-1 flex items-center overflow-hidden'
              }
            >
              {editingAssignee ? (
                <>
                  <Select
                    allowClear
                    showSearch
                    options={userOptions}
                    value={selectedAssignees}
                    maxTagCount={1}
                    mode="multiple"
                    className="flex-1 mr-[10px]"
                    filterOption={(input, option) =>
                      (option?.label as string)
                        ?.toLowerCase()
                        .includes(input.toLowerCase())
                    }
                    onChange={setSelectedAssignees}
                  />
                  <Button
                    size="small"
                    type="link"
                    icon={<CheckOutlined />}
                    loading={assigneeLoading}
                    disabled={!selectedAssignees.length}
                    onClick={confirmAssignee}
                  />
                  <Button
                    size="small"
                    type="link"
                    icon={<CloseOutlined />}
                    onClick={cancelAssignee}
                  />
                </>
              ) : (
                <>
                  <EllipsisWithTooltip
                    className="whitespace-nowrap overflow-hidden text-ellipsis mr-[6px]"
                    text={assigneeDisplay || '--'}
                  ></EllipsisWithTooltip>
                  <PermissionWrapper requiredPermissions={['Edit']}>
                    <Button
                      size="small"
                      type="link"
                      icon={<EditOutlined />}
                      className="mr-[10px]"
                      onClick={() => setEditingAssignee(true)}
                    />
                  </PermissionWrapper>
                </>
              )}
            </div>
          </Descriptions.Item>
        );
      }
      if (key === 'note') {
        return (
          <Descriptions.Item label={label} key={idx}>
            <div className={styles.descContent + ' flex-1 flex items-center'}>
              {editingNote ? (
                <>
                  <Input.TextArea
                    rows={3}
                    style={{ width: '220px', marginRight: '10px' }}
                    value={noteValue}
                    onChange={(e) => setNoteValue(e.target.value)}
                  />
                  <Button
                    size="small"
                    type="link"
                    icon={<CheckOutlined />}
                    onClick={confirmNote}
                    loading={noteLoading}
                    disabled={noteValue === preNote}
                  />
                  <Button
                    size="small"
                    type="link"
                    icon={<CloseOutlined />}
                    onClick={cancelNote}
                  />
                </>
              ) : (
                <>
                  <EllipsisWithTooltip
                    className="whitespace-nowrap overflow-hidden text-ellipsis mr-[6px] max-w-[280px]"
                    text={preNote || '--'}
                  />
                  <PermissionWrapper requiredPermissions={['Edit']}>
                    <Button
                      size="small"
                      type="link"
                      icon={<EditOutlined />}
                      onClick={() => setEditingNote(true)}
                    />
                  </PermissionWrapper>
                </>
              )}
            </div>
          </Descriptions.Item>
        );
      }
      return (
        <Descriptions.Item label={label} key={idx}>
          <div className={styles.descContent}>
            {incidentDetail?.[key] || '--'}
          </div>
        </Descriptions.Item>
      );
    });

  const descFields = [
    { label: t('alarms.createTime'), key: 'created_at' },
    { label: t('alarms.source'), key: 'sources' },
    {
      label: t('alarms.state'),
      key: 'status',
    },
    { label: t('alarms.assignee'), key: 'operator_users' },
    { label: t('alarms.note'), key: 'note' },
  ];

  return (
    <div className={styles.detailContainer}>
      <div style={{ position: 'relative', marginBottom: '16px' }}>
        <CustomBreadcrumb>
          <Breadcrumb.Item>
            <span className="mr-[10px]">{incidentDetail?.title}</span>
            {incidentDetail && (
              <Tag
                color={
                  levelMapIncident[incidentDetail?.level as string] as string
                }
              >
                <div className="flex items-center">
                  <Icon
                    type={
                      levelListIncident.find(
                        (item) =>
                          item.level_id === Number(incidentDetail?.level)
                      )?.icon || ''
                    }
                    className="mr-1"
                  />
                  {levelListIncident.find(
                    (item) => item.level_id === Number(incidentDetail?.level)
                  )?.level_display_name || '--'}
                </div>
              </Tag>
            )}
          </Breadcrumb.Item>
        </CustomBreadcrumb>
        <Button
          type="text"
          icon={<ReloadOutlined />}
          onClick={onRefresh}
          style={{
            position: 'absolute',
            top: 0,
            right: 0,
          }}
        />
      </div>
      <div className={styles.detailContent}>
        {loadingDetail ? (
          <div className="flex justify-center pt-[20px] h-[72px] ">
            <Spin spinning={loadingDetail}></Spin>
          </div>
        ) : (
          <Descriptions
            column={{ xs: 1, sm: 2, md: 3, lg: 3, xl: 4, xxl: 4 }}
            size="default"
            className={styles.descriptions}
          >
            {renderDescItems()}
          </Descriptions>
        )}
        <div className={`${styles.tabsWrapper} w-full`}>
          <Tabs defaultActiveKey="alert">
            <TabPane tab={t('alarms.alert')} key="alert">
              <div className={styles.tabContent}>
                <div className={styles.filterRow}>
                  <div className={styles.switchWrapper}>
                    <SearchFilter
                      attrList={alarmAttrList}
                      onSearch={(condition) => {
                        setSelectedRowKeys([]);
                        fetchAlarmList(undefined, condition);
                      }}
                    />
                    <Segmented
                      className="ml-[12px]"
                      defaultValue="table"
                      options={[
                        {
                          value: 'table',
                          label: t('incidents.table'),
                          icon: <AppstoreOutlined />,
                        },
                        {
                          value: 'gantt',
                          label: (
                            <span className="inline-flex items-center">
                              <Icon type="gantetu" className="mr-1" />
                              {t('incidents.gantt')}
                            </span>
                          ),
                        },
                      ]}
                      onChange={setViewType as any}
                    />
                  </div>
                  <div>
                    <PermissionWrapper requiredPermissions={['Edit']}>
                      <Button
                        type="primary"
                        className="mr-[12px]"
                        onClick={() => handleLink()}
                      >
                        {t('alarmCommon.linkAlert')}
                      </Button>
                    </PermissionWrapper>
                    <PermissionWrapper requiredPermissions={['Edit']}>
                      <Button
                        disabled={!selectedRowKeys.length}
                        type="primary"
                        onClick={() => handleUnlink()}
                        loading={unlinkLoading}
                      >
                        {t('alarmCommon.unlinkAlert')}
                      </Button>
                    </PermissionWrapper>
                  </div>
                </div>
                {viewType === 'table' ? (
                  <AlarmTable
                    dataSource={tableData}
                    loading={tabLoading}
                    tableScrollY="calc(100vh - 430px)"
                    selectedRowKeys={selectedRowKeys}
                    onChange={onTabTableChange}
                    onSelectionChange={setSelectedRowKeys}
                    onRefresh={() => fetchAlarmList()}
                    extraActions={(record) => (
                      <PermissionWrapper requiredPermissions={['Edit']}>
                        <Button
                          type="link"
                          className="mr-[12px]"
                          onClick={() => handleUnlink([record.id as number])}
                          loading={rowUnlinkKey === record.id}
                        >
                          {t('alarmCommon.unlinkAlert')}
                        </Button>
                      </PermissionWrapper>
                    )}
                  />
                ) : (
                  <GanttChart
                    loading={tabLoading}
                    alarmData={tableData}
                    selectedTasks={selectedRowKeys as number[]}
                    onSelectionChange={(keys) => setSelectedRowKeys(keys)}
                  />
                )}
              </div>
            </TabPane>
            <TabPane tab={t('alarms.changes')} key="timeline">
              <Spin spinning={recordLoading}>
                {timeLineData.length > 1 ? (
                  <div className={styles.timelineContent}>
                    <Timeline items={timeLineData} />
                  </div>
                ) : (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={t('common.noData')}
                  />
                )}
              </Spin>
            </TabPane>
          </Tabs>
        </div>
      </div>
      <LinkModal
        visible={operateVisible}
        onClose={() => setOperateVisible(false)}
        onLink={handleLinkConfirm}
        confirmLoading={linkingLoading}
      />
    </div>
  );
};

export default IncidentDetail;
