import { BUILD_IN_MODEL, CREDENTIAL_LIST } from '@/app/cmdb/constants/asset';
import { getSvgIcon } from './utils';
import dayjs from 'dayjs';
import { AttrFieldType } from '@/app/cmdb/types/assetManage';
import {
  Tag,
  Select,
  Input,
  InputNumber,
  DatePicker,
  Tooltip,
  Table,
  Popover,
  Button,
  Space,
  message,
} from 'antd';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import GroupTreeSelector from '@/components/group-tree-select';
import CollectTaskTreeSelect from '@/app/cmdb/components/collect-task-tree-select';
import { useUserInfoContext } from '@/context/userInfo';
import UserAvatar from '@/components/user-avatar';
import React from 'react';
import { useTranslation } from '@/utils/i18n';
import {
  ModelIconItem,
  ColumnItem,
  UserItem,
  SubGroupItem,
  OriginOrganization,
  OriginSubGroupItem,
  EnumList,
  TimeAttrOption,
  StrAttrOption,
  IntAttrOption,
  AttrLike,
  TableColumnSpec,
  TagAttrOption,
} from '@/app/cmdb/types/assetManage';
import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';
import {
  getCollectTaskLinkMeta,
} from '@/app/cmdb/utils/collectTask';
import TableFieldEditor from './tableFieldEditor';
import TagCascaderEditor from './tagCascaderEditor';
import TagCapsuleGroup from '@/app/cmdb/components/tag-capsule-group';
import { getTagDisplayText } from '@/app/cmdb/utils/tag';

// 解析表格字段值（支持 JSON 字符串或数组）
export const parseTableValue = (val: any): any[] => {
  if (!val) return [];
  if (typeof val === 'string') {
    try { return JSON.parse(val); } catch { return []; }
  }
  return Array.isArray(val) ? val : [];
};

type TableRowData = Record<string, unknown>;

const getSortedTableColumns = (columns: TableColumnSpec[] = []) =>
  [...columns].sort((a, b) => a.order - b.order);

const formatTableCellText = (value: unknown): string => {
  if (value === undefined || value === null || value === '') {
    return '--';
  }
  return String(value);
};

const getTablePlainText = (
  tableData: TableRowData[],
  sortedCols: TableColumnSpec[]
): string => {
  const header = sortedCols.map((col) => col.column_name).join('\t');
  const rows = tableData.map((row) =>
    sortedCols
      .map((col) => formatTableCellText(row[col.column_id]))
      .join('\t')
  );

  return [header, ...rows].join('\n');
};

const escapeCsvValue = (value: unknown): string => {
  const text = value === undefined || value === null ? '' : String(value);
  const escaped = text.replace(/"/g, '""');
  return /[",\r\n]/.test(text) ? `"${escaped}"` : escaped;
};

const downloadTableCsv = (
  fileName: string,
  sortedCols: TableColumnSpec[],
  tableData: TableRowData[]
) => {
  const header = sortedCols.map((col) => escapeCsvValue(col.column_name)).join(',');
  const rows = tableData.map((row) =>
    sortedCols
      .map((col) => escapeCsvValue(row[col.column_id]))
      .join(',')
  );
  const csvContent = ['\uFEFF' + header, ...rows].join('\r\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');

  link.href = url;
  link.download = fileName.endsWith('.csv') ? fileName : `${fileName}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

const TableFieldReadonlyDisplay: React.FC<{
  fieldName: string;
  tableData: TableRowData[];
  tableColumns: TableColumnSpec[];
}> = ({ fieldName, tableData, tableColumns }) => {
  const { t } = useTranslation();

  const sortedCols = React.useMemo(
    () => getSortedTableColumns(tableColumns),
    [tableColumns]
  );

  const viewerColumns = React.useMemo(
    () =>
      sortedCols.map((col) => ({
        title: col.column_name,
        dataIndex: col.column_id,
        key: col.column_id,
        width: col.column_type === 'number' ? 160 : 220,
        render: (value: unknown) => (
          <EllipsisWithTooltip
            text={formatTableCellText(value)}
            className="block w-full whitespace-nowrap overflow-hidden text-ellipsis"
          />
        ),
      })),
    [sortedCols]
  );
  const tableScrollX = React.useMemo(() => {
    const totalColumnWidth = sortedCols.reduce((sum, col) => {
      return sum + (col.column_type === 'number' ? 160 : 220);
    }, 0);

    return Math.max(totalColumnWidth, 960);
  }, [sortedCols]);

  const handleExport = () => {
    try {
      downloadTableCsv(
        `${fieldName}_${dayjs().format('YYYYMMDD_HHmmss')}`,
        sortedCols,
        tableData
      );
      message.success(t('Model.exportSuccess'));
    } catch (error: unknown) {
      const errorMessage =
        error instanceof Error ? error.message : t('Model.exportFailed');
      message.error(errorMessage || t('Model.exportFailed'));
    }
  };

  return (
    <div className="w-full rounded border border-[var(--color-border-1,var(--ant-color-border-secondary))] bg-[var(--color-bg-1)] p-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-xs text-[var(--color-text-3)]">
          {tableData.length} rows
        </div>
        <Space size={4} className="flex-shrink-0">
          <Button type="link" size="small" onClick={handleExport}>
            {t('common.export')}
          </Button>
        </Space>
      </div>
      <Table
        dataSource={tableData}
        columns={viewerColumns}
        pagination={false}
        size="small"
        tableLayout="fixed"
        scroll={{ x: tableScrollX, y: 420 }}
        style={{ width: '100%' }}
        rowKey={(_, index) => String(index)}
        className="[&_.ant-table-thead_th]:!py-2 [&_.ant-table-tbody_td]:!py-2 [&_.ant-table-thead_th]:text-xs [&_.ant-table-thead_th:first-child]:!rounded-none [&_.ant-table-thead_th:last-child]:!rounded-none"
      />
    </div>
  );
};

const collectTaskLinkClassName =
  'text-[var(--color-primary)] underline cursor-pointer hover:text-[var(--color-primary-hover,#3a84ff)]';

const renderCollectTaskValue = (value: unknown) => {
  // Given 实例页需要按任务跳转采集详情，When 拿到 collect_task 值，Then 先解析是否可生成完整路由。
  const meta = getCollectTaskLinkMeta(value);
  if (!meta.clickable || !meta.href) {
    return (
      <EllipsisWithTooltip
        className="whitespace-nowrap overflow-hidden text-ellipsis"
        text={meta.displayText}
      />
    );
  }

  return (
    <a
      href={meta.href}
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-block max-w-full whitespace-nowrap overflow-hidden text-ellipsis ${collectTaskLinkClassName}`}
      title={meta.displayText}
    >
      {meta.displayText}
    </a>
  );
};

type UserDisplayContext = 'table' | 'detail';

interface UserDisplayResult {
  users: UserItem[];
  isEmpty: boolean;
}

const resolveUsers = (
  value: unknown,
  userList: UserItem[]
): UserDisplayResult => {
  if (Array.isArray(value) && value.length > 0) {
    const userIdsStr = value.map((id) => String(id));
    const users = userList.filter((user) => userIdsStr.includes(String(user.id)));
    return { users, isEmpty: users.length === 0 };
  }
  if (value !== null && value !== undefined && value !== '') {
    const user = userList.find((item) => String(item.id) === String(value));
    return { users: user ? [user] : [], isEmpty: !user };
  }
  return { users: [], isEmpty: true };
};

const formatUserName = (user: UserItem): string =>
  `${user.display_name}(${user.username})`;

export const renderUserDisplay = (
  value: unknown,
  userList: UserItem[],
  context: UserDisplayContext,
  hideUserAvatar = false
): React.ReactNode => {
  const { users, isEmpty } = resolveUsers(value, userList);
  
  if (isEmpty) {
    return context === 'detail' ? '--' : <>--</>;
  }

  if (context === 'table') {
    return (
      <div className="flex items-center gap-2 max-h-[28px] overflow-hidden">
        <UserAvatar key={users[0].id} userName={formatUserName(users[0])} size="small" />
        {users.length > 1 && (
          <Tooltip
            title={
              <div className="flex flex-col gap-1">
                {users.map((user) => (
                  <div key={user.id}>{formatUserName(user)}</div>
                ))}
              </div>
            }
          >
            <span className="text-[var(--color-text-3)] cursor-pointer">...</span>
          </Tooltip>
        )}
      </div>
    );
  }

  if (hideUserAvatar) {
    return users.map((u) => formatUserName(u)).join('，');
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {users.map((user) => (
        <UserAvatar key={user.id} userName={formatUserName(user)} />
      ))}
    </div>
  );
};

// 查找组织对象
const findOrganizationById = (arr: Array<any>, targetValue: unknown) => {
  for (let i = 0; i < arr.length; i++) {
    if (arr[i].id === targetValue || arr[i].value === targetValue) {
      return arr[i];
    }
  }
  return null;
};

// 获取组织的完整路径（从根到当前节点）
const getOrganizationFullPath = (org: any, flatGroups: Array<any>): string => {
  if (!org) return '';
  const path: string[] = [];
  let current = org;
  while (current) {
    const name = current.name || current.label;
    if (name) {
      path.unshift(name);
    }
    const parentId = current.parent_id || current.parentId;
    if (parentId) {
      current = findOrganizationById(flatGroups, parentId);
    } else {
      break;
    }
  }
  return path.join('/');
};

// 通用的组织显示文本处理函数
export const getOrganizationDisplayText = (value: any, flatGroups: Array<any>) => {
  if (Array.isArray(value)) {
    if (value.length === 0) return '--';
    const groupNames = value
      .map((val) => {
        const org = findOrganizationById(flatGroups || [], val);
        return org ? getOrganizationFullPath(org, flatGroups) : null;
      })
      .filter((name) => name !== null && name !== '');
    return groupNames.length > 0 ? groupNames.join('，') : '--';
  } else {
    const org = findOrganizationById(flatGroups || [], value);
    const fullPath = org ? getOrganizationFullPath(org, flatGroups) : '';
    return fullPath || '--';
  }
};

// 组织字段显示组件
const OrganizationDisplay: React.FC<{ value: any }> = ({ value }) => {
  const { flatGroups } = useUserInfoContext();

  return (
    <EllipsisWithTooltip
      className="whitespace-nowrap overflow-hidden text-ellipsis"
      text={getOrganizationDisplayText(value, flatGroups)}
    />
  );
};

// 组织字段编辑/显示工具组件
export const OrganizationField: React.FC<{ value: any; hideUserAvatar?: boolean }> = ({
  value,
}) => {
  const { flatGroups } = useUserInfoContext();
  return getOrganizationDisplayText(value, flatGroups);
};

export const iconList = getSvgIcon();
export function getIconUrl(tex: ModelIconItem) {
  try {
    const icon = tex.icn?.split('icon-')[1];

    // 查找显示的图标
    const showIcon = iconList.find((item) => item.key === icon);

    // 如果显示图标存在，直接返回相应的图标路径
    if (showIcon) {
      return `/app/assets/assetModelIcon/${showIcon.url}.svg`;
    }

    // 查找内置模型和对应图标
    const isBuilt = BUILD_IN_MODEL.find((item) => item.key === tex.model_id);
    const builtIcon = isBuilt
      ? iconList.find((item) => item.key === isBuilt.icon)
      : null;

    // 使用内置模型图标或者默认图标
    const iconUrl = builtIcon?.url || 'cc-default_默认';

    // 返回图标路径
    return `/app/assets/assetModelIcon/${iconUrl}.svg`;
  } catch (e) {
    // 记录错误日志并返回默认图标
    console.error('Error in getIconUrl:', e);
    return 'app/assets/assetModelIcon/cc-default_默认.svg';
  }
}

// 深克隆
export const deepClone = (obj: any, hash = new WeakMap()) => {
  if (Object(obj) !== obj) return obj;
  if (obj instanceof Set) return new Set(obj);
  if (hash.has(obj)) return hash.get(obj);

  const result =
    obj instanceof Date
      ? new Date(obj)
      : obj instanceof RegExp
        ? new RegExp(obj.source, obj.flags)
        : dayjs.isDayjs(obj)
          ? obj.clone()
          : obj.constructor
            ? new obj.constructor()
            : Object.create(null);

  hash.set(obj, result);

  if (obj instanceof Map) {
    Array.from(obj, ([key, val]) => result.set(key, deepClone(val, hash)));
  }

  // 如果是 dayjs 对象，直接返回克隆后的对象
  if (dayjs.isDayjs(obj)) {
    return result;
  }

  // 复制函数
  if (typeof obj === 'function') {
    return function (this: unknown, ...args: unknown[]): unknown {
      return obj.apply(this, args);
    };
  }

  // 递归复制对象的其他属性
  for (const key in obj) {
    if (obj.hasOwnProperty(key)) {
      // File不做处理
      if (obj[key] instanceof File) {
        result[key] = obj[key];
        continue;
      }
      result[key] = deepClone(obj[key], hash);
    }
  }

  return result;
};

export const findGroupNameById = (arr: Array<SubGroupItem>, value: unknown) => {
  for (let i = 0; i < arr.length; i++) {
    if (arr[i].value === value) {
      return arr[i].label;
    }
    if (arr[i].children && arr[i].children?.length) {
      const label: unknown = findGroupNameById(arr[i]?.children || [], value);
      if (label) {
        return label;
      }
    }
  }
  return null;
};

// 根据数组id找出对应名称（多选）
export const findNameByIds = (list: Array<any>, ids: Array<string>) => {
  const map = new Map(list.map((i) => [i.id, i.name]));
  return ids.map((id) => map.get(id)).join('，') || '--';
};

// 组织改造成联级数据
export const convertArray = (
  arr: Array<OriginOrganization | OriginSubGroupItem>
) => {
  const result: any = [];
  arr.forEach((item) => {
    const newItem = {
      value: item.id,
      label: item.name,
      children: [],
    };
    const subGroups: OriginSubGroupItem[] = item.subGroups;
    if (subGroups && !!subGroups.length) {
      newItem.children = convertArray(subGroups);
    }
    result.push(newItem);
  });
  return result;
};

export const getAssetColumns = (config: {
  attrList: AttrFieldType[];
  userList?: UserItem[];
  t?: any;
}): ColumnItem[] => {
  return config.attrList.map((item: AttrFieldType) => {
    const attrType = item.attr_type;
    const attrId = item.attr_id;
    const columnItem: ColumnItem = {
      title: item.attr_name,
      dataIndex: attrId,
      key: attrId,
      width: 180,
      fixed: attrId === 'inst_name' ? 'left' : undefined,
      ellipsis: {
        showTitle: false,
      },
    };
    switch (attrType) {
      case 'user':
        return {
          ...columnItem,
          render: (_: unknown, record: any) => (
            <>{renderUserDisplay(record[attrId], config.userList || [], 'table')}</>
          ),
        };
      case 'pwd':
        return {
          ...columnItem,
          render: () => <>***</>,
        };
      case 'organization':
        return {
          ...columnItem,
          render: (_: unknown, record: any) => (
            <OrganizationDisplay value={record[attrId]} />
          ),
        };
      case 'bool':
        return {
          ...columnItem,
          render: (_: unknown, record: any) => (
            <>
              <Tag color={record[attrId] ? 'green' : 'geekblue'}>
                {record[attrId] ? 'Yes' : 'No'}
              </Tag>
            </>
          ),
        };
      case 'enum':
        return {
          ...columnItem,
          render: (_: unknown, record: any) => {
            const enumOptions = Array.isArray(item.option) ? (item.option as EnumList[]) : [];
            const rawValue = record[attrId];
            const valueArray = Array.isArray(rawValue) ? rawValue : (rawValue ? [rawValue] : []);
            if (valueArray.length === 0) return <>--</>;
            const displayNames = valueArray
              .map((val: string) => enumOptions.find((opt: EnumList) => opt.id === val)?.name)
              .filter(Boolean);
            return displayNames.length > 0 ? <>{displayNames.join(', ')}</> : <>--</>;
          },
        };
      case 'table': {
        return {
          ...columnItem,
          render: (_: unknown, record: any) => {
            const tableData = parseTableValue(record[attrId]);
            
            const tableColumns = (item.option as TableColumnSpec[]) || [];
            
            if (!tableData.length || !tableColumns.length) return <>--</>;
            
            const sortedCols = [...tableColumns].sort((a, b) => a.order - b.order);
            const firstColId = sortedCols[0]?.column_id;
            
            if (!firstColId) return <>--</>;
            
            const firstColValues = tableData.map(row => row[firstColId]).filter(v => v !== undefined && v !== '');
            const displayValues = firstColValues.slice(0, 2);
            const remainingCount = firstColValues.length - 2;
            
            const fullTableContent = (
              <div className="max-w-[min(600px,calc(100vw-48px))] max-h-[min(400px,calc(100vh-120px))] overflow-auto">
                <Table
                  dataSource={tableData}
                  columns={sortedCols.map(col => ({
                    title: col.column_name,
                    dataIndex: col.column_id,
                    key: col.column_id,
                    width: col.column_type === 'number' ? 160 : 220,
                    render: (value: unknown) => (
                      <EllipsisWithTooltip
                        text={formatTableCellText(value)}
                        className="block w-full whitespace-nowrap overflow-hidden text-ellipsis"
                      />
                    ),
                  }))}
                  pagination={false}
                  size="small"
                  tableLayout="fixed"
                  scroll={{ x: Math.max(sortedCols.reduce((sum, col) => sum + (col.column_type === 'number' ? 160 : 220), 0), 720), y: 320 }}
                  rowKey={(_, index) => String(index)}
                />
              </div>
            );
            
            return (
              <Popover
                content={fullTableContent}
                trigger="hover"
                placement="bottomLeft"
              >
                <div className="flex items-center gap-1 flex-wrap cursor-pointer">
                  {displayValues.map((val, idx) => (
                    <span
                      key={idx}
                      className="inline-block px-2 py-0.5 text-xs rounded bg-[var(--color-bg-4)] text-[var(--color-text-1)]"
                    >
                      {String(val)}
                    </span>
                  ))}
                  {remainingCount > 0 && (
                    <span className="ml-2 text-xs text-[var(--color-primary)]">
                      +{remainingCount}
                    </span>
                  )}
                </div>
              </Popover>
            );
          },
        };
      }
      case 'tag':
        return {
          ...columnItem,
          render: (_: unknown, record: any) => {
            return <TagCapsuleGroup value={record[attrId]} maxVisible={2} compact />;
          },
        };
      case 'time': {
        const timeOption = item.option as TimeAttrOption | undefined;
        const dateFormat = timeOption?.display_format === 'date' ? 'YYYY-MM-DD' : 'YYYY-MM-DD HH:mm:ss';
        return {
          ...columnItem,
          render: (_: unknown, record: any) => {
            const val = record[attrId];
            if (Array.isArray(val)) {
              return (
                <>
                  {dayjs(val[0]).format(dateFormat)} -{' '}
                  {dayjs(val[1]).format(dateFormat)}
                </>
              );
            }
            return (
              <> {val ? dayjs(val).format(dateFormat) : '--'} </>
            );
          },
        };
      }
      default:
        return {
          ...columnItem,
          render: (_: unknown, record: any) => {
            const cloudOptions = useAssetDataStore.getState().cloud_list;
            const modelId = record.model_id;
            if (attrId === 'cloud' && modelId === 'host') {
              const cloudId = +record[attrId];
              const cloudName = cloudOptions.find(
                (option: any) => option.proxy_id === cloudId
              );
              const displayText = cloudName ? cloudName.proxy_name : (cloudName || '--');
              return (
                <EllipsisWithTooltip
                  className="whitespace-nowrap overflow-hidden text-ellipsis"
                  text={displayText as string}
                ></EllipsisWithTooltip>
              );
            }

            if (attrId === 'collect_task') {
              return renderCollectTaskValue(record[attrId]);
            }

            return (
              <EllipsisWithTooltip
                className="whitespace-nowrap overflow-hidden text-ellipsis"
                text={record[attrId] || '--'}
              ></EllipsisWithTooltip>
            );
          },
        };
    }
  });
};


export const getFieldItem = (config: {
  fieldItem: AttrFieldType;
  userList?: UserItem[];
  isEdit: boolean;
  value?: any;
  hideUserAvatar?: boolean;
  disabled?: boolean;
  placeholder?: string;
  flatGroups?: Array<{ id: string; name: string; parentId?: string }>;
  inModal?: boolean;
}) => {
  const { disabled, placeholder } = config;
  if (config.isEdit) {
    if (config.fieldItem.attr_id === 'collect_task') {
      return (
        <CollectTaskTreeSelect
          disabled={disabled}
          placeholder={placeholder}
        />
      );
    }
    switch (config.fieldItem.attr_type) {
      case 'user':
        return (
          // 新增+编辑弹窗中，用户字段为多选
          <Select
            mode="multiple"
            showSearch
            disabled={disabled}
            placeholder={placeholder}
            filterOption={(input, opt: any) => {
              if (typeof opt?.children?.props?.text === 'string') {
                return opt?.children?.props?.text
                  ?.toLowerCase()
                  .includes(input.toLowerCase());
              }
              return true;
            }}
          >
            {config.userList?.map((opt: UserItem) => (
              <Select.Option key={opt.id} value={opt.id}>
                <EllipsisWithTooltip
                  text={`${opt.display_name}(${opt.username})`}
                  className="whitespace-nowrap overflow-hidden text-ellipsis break-all"
                />
              </Select.Option>
            ))}
          </Select>
        );
      case 'enum':
        const enumOpts = Array.isArray(config.fieldItem.option)
          ? config.fieldItem.option
          : [];
        const isMultipleEnum = config.fieldItem.enum_select_mode === 'multiple';
        return (
          <Select
            mode={isMultipleEnum ? 'multiple' : undefined}
            showSearch
            disabled={disabled}
            placeholder={placeholder}
            filterOption={(input, opt: any) => {
              if (typeof opt?.children === 'string') {
                return opt?.children
                  ?.toLowerCase()
                  .includes(input.toLowerCase());
              }
              return true;
            }}
          >
            {enumOpts.map((opt) => (
              <Select.Option key={opt.id} value={opt.id}>
                {opt.name}
              </Select.Option>
            ))}
          </Select>
        );
      case 'bool':
        return (
          <Select disabled={disabled} placeholder={placeholder}>
            {[
              { id: true, name: 'Yes' },
              { id: false, name: 'No' },
            ].map((opt: any) => (
              <Select.Option key={opt.id} value={opt.id}>
                {opt.name}
              </Select.Option>
            ))}
          </Select>
        );
      case 'organization':
        return <GroupTreeSelector multiple={true} disabled={disabled} />;
      case 'time':
        const timeOption = config.fieldItem.option as TimeAttrOption;
        const displayFormat = timeOption?.display_format || 'datetime';
        const showTime = displayFormat === 'datetime';
        const format =
          displayFormat === 'datetime' ? 'YYYY-MM-DD HH:mm:ss' : 'YYYY-MM-DD';
        return (
          <DatePicker
            showTime={showTime}
            format={format}
            disabled={disabled}
            placeholder={placeholder}
            style={{ width: '100%' }}
          />
        );
      case 'int':
        const intOption = config.fieldItem.option as IntAttrOption;
        return (
          <InputNumber
            style={{ width: '100%' }}
            disabled={disabled}
            placeholder={placeholder}
            min={
              ![undefined, '', null].includes(intOption?.min_value as string)
                ? Number(intOption.min_value)
                : undefined
            }
            max={
              ![undefined, '', null].includes(intOption?.max_value as string)
                ? Number(intOption.max_value)
                : undefined
            }
          />
        );
      case 'table':
        return (
          <TableFieldEditor
            columns={config.fieldItem.option as TableColumnSpec[]}
            disabled={disabled}
            inModal={config.inModal}
          />
        );
      case 'tag': {
        const tagOption = (config.fieldItem.option || {}) as TagAttrOption;
        return (
          <TagCascaderEditor
            option={tagOption}
            disabled={disabled}
            placeholder={placeholder}
          />
        );
      }
      default:
        if (config.fieldItem.attr_type === 'str') {
          const strOption = config.fieldItem.option as StrAttrOption;
          if (strOption?.widget_type === 'multi_line') {
            return (
              <Input.TextArea
                rows={3}
                disabled={disabled}
                placeholder={placeholder}
              />
            );
          }
        }
        return <Input disabled={disabled} placeholder={placeholder} />;
    }
  }
  switch (config.fieldItem.attr_type) {
    case 'user':
      return renderUserDisplay(
        config.value,
        config.userList || [],
        'detail',
        config.hideUserAvatar,
      );
    case 'organization':
      if (config.hideUserAvatar && config.flatGroups) {
        return getOrganizationDisplayText(config.value, config.flatGroups);
      }
      return (
        <OrganizationField
          value={config.value}
          hideUserAvatar={config.hideUserAvatar}
        />
      );
    case 'bool':
      return config.value ? 'Yes' : 'No';
    case 'enum':
      const enumOptions = Array.isArray(config.fieldItem.option)
        ? (config.fieldItem.option as EnumList[])
        : [];
      if (Array.isArray(config.value)) {
        if (config.value.length === 0) return '--';
        const enumNames = config.value
          .map((val: any) => {
            return enumOptions.find((item: EnumList) => item.id === val)?.name;
          })
          .filter((name) => name !== undefined)
          .join('，');
        return enumNames || '--';
      }
      return (
        enumOptions.find((item: EnumList) => item.id === config.value)?.name ||
        '--'
      );
    case 'str':
      if (config.fieldItem.attr_id === 'collect_task') {
        // Given 详情页字段为只读展示，When collect_task 可解析路由，Then 渲染可点击新标签链接。
        const meta = getCollectTaskLinkMeta(config.value);
        if (config.hideUserAvatar || !meta.clickable || !meta.href) {
          return meta.displayText;
        }
        return (
          <a
            href={meta.href}
            target="_blank"
            rel="noopener noreferrer"
            className={collectTaskLinkClassName}
            title={meta.displayText}
          >
            {meta.displayText}
          </a>
        );
      }
      return config.value || '--';
    case 'table':
      const tableData = parseTableValue(config.value);
      const tableColumns = config.fieldItem.option as TableColumnSpec[];
      if (!tableData.length || !tableColumns?.length) return '--';

      const sortedCols = getSortedTableColumns(tableColumns);

      if (config.hideUserAvatar) {
        return getTablePlainText(tableData, sortedCols);
      }

      return (
        <TableFieldReadonlyDisplay
          fieldName={config.fieldItem.attr_name}
          tableData={tableData}
          tableColumns={tableColumns}
        />
      );
    case 'tag':
      return getTagDisplayText(config.value);
    default:
      if (config.fieldItem.attr_type === 'time' && config.value) {
        const timeOpt = config.fieldItem.option as TimeAttrOption;
        const displayFmt = timeOpt?.display_format || 'datetime';
        const fmt =
          displayFmt === 'datetime' ? 'YYYY-MM-DD HH:mm:ss' : 'YYYY-MM-DD';
        return dayjs(config.value).format(fmt);
      }
      return config.value || '--';
  }
};

export const findAndFlattenAttrs = (modelId: string) => {
  let resultAttrs: AttrFieldType[] = [];
  function flattenChildren(attrs: AttrFieldType[]) {
    const flattenedAttrs: any[] = [];
    attrs.forEach((attr: AttrFieldType) => {
      const { children, ...rest } = attr;
      flattenedAttrs.push(rest);
      if (children?.length) {
        const nestedAttrs = flattenChildren(children);
        flattenedAttrs.push(...nestedAttrs);
      }
    });
    return flattenedAttrs;
  }
  function searchModel(list: any[]) {
    for (const item of list) {
      if (item.model_id === modelId) {
        resultAttrs = flattenChildren(item.attrs);
        return;
      } else if (item.list?.length) {
        searchModel(item.list);
      }
    }
  }
  searchModel(CREDENTIAL_LIST);
  return resultAttrs;
};

// 用于查节点及其所有父级节点
export const findNodeWithParents: any = (
  nodes: any[],
  id: string,
  parent: any = null
) => {
  for (const node of nodes) {
    if (node.id === id) {
      return parent ? [node, ...findNodeWithParents(nodes, parent.id)] : [node];
    }
    if (node.subGroups && node.subGroups.length > 0) {
      const result: any = findNodeWithParents(node.subGroups, id, node);
      if (result) {
        return result;
      }
    }
  }
  return [];
};

// 过滤出所有给定ID的节点及其所有父级节点
export const filterNodesWithAllParents = (nodes: any, ids: any[]) => {
  const result: any[] = [];
  const uniqueIds: any = new Set(ids);
  for (const id of uniqueIds) {
    const nodeWithParents = findNodeWithParents(nodes, id);
    if (nodeWithParents) {
      for (const node of nodeWithParents) {
        if (!result.find((n) => n.id === node.id)) {
          result.push(node);
        }
      }
    }
  }
  return result;
};

export const VALIDATION_PATTERNS: Record<string, RegExp> = {
  ipv4: /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/,
  ipv6: /^(([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|(([0-9a-fA-F]{1,4}:){1,6}|:):((:[0-9a-fA-F]{1,4}){1,6}|:)|::([fF]{4}(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))$/,
  email: /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/,
  mobile_phone: /^1[3-9]\d{9}$/,
  url: /^(https?|ftp):\/\/[^\s/$.?#].[^\s]*$/,
  json: /^[\s]*(\{[\s\S]*\}|\[[\s\S]*\])[\s]*$/,
};

export const getStringValidationRule = (item: AttrLike, t: (key: string) => string) => {
  const strOption = item.option as StrAttrOption;
  if (!strOption?.validation_type || strOption.validation_type === 'unrestricted') {
    return null;
  }
  if (strOption.validation_type === 'custom' && strOption.custom_regex) {
    try {
      return {
        pattern: new RegExp(strOption.custom_regex),
        message: t('Model.validationRuleMessage'),
      };
    } catch {
      return null;
    }
  }
  if (VALIDATION_PATTERNS[strOption.validation_type]) {
    return {
      pattern: VALIDATION_PATTERNS[strOption.validation_type],
      message: t('Model.validationRuleMessage'),
    };
  }
  return null;
};

export const getNumberRangeRule = (item: AttrLike, t: (key: string) => string) => {
  const intOption = item.option as IntAttrOption;
  const hasMin = ![undefined, '', null].includes(intOption?.min_value as string);
  const hasMax = ![undefined, '', null].includes(intOption?.max_value as string);
  if (!hasMin && !hasMax) return null;
  return {
    validator: (_: unknown, value: unknown) => {
      if ([undefined, null, ''].includes(value as string)) {
        return Promise.resolve();
      }
      const numValue = Number(value);
      if (hasMin && numValue < Number(intOption.min_value)) {
        return Promise.reject(new Error(t('Model.validationRuleMessage')));
      }
      if (hasMax && numValue > Number(intOption.max_value)) {
        return Promise.reject(new Error(t('Model.validationRuleMessage')));
      }
      return Promise.resolve();
    },
  };
};

export const getValidationRules = (item: AttrLike, t: (key: string) => string) => {
  const rules: any[] = [];
  if (item.is_required) {
    rules.push({ required: true, message: '' });
  }
  if (item.attr_type === 'str') {
    const strRule = getStringValidationRule(item, t);
    if (strRule) rules.push(strRule);
  } else if (item.attr_type === 'int') {
    const intRule = getNumberRangeRule(item, t);
    if (intRule) rules.push(intRule);
  }
  return rules;
};

export const normalizeTimeValueForForm = (item: AttrLike, value: unknown) => {
  if (item.attr_type === 'time' && value && typeof value === 'string') {
    return dayjs(value, 'YYYY-MM-DD HH:mm:ss');
  }
  return value;
};

export const normalizeTimeValueForSubmit = (item: AttrLike, value: unknown) => {
  if (item.attr_type === 'time' && dayjs.isDayjs(value)) {
    const timeOption = item.option as TimeAttrOption;
    // date 格式约定: YYYY-MM-DD 00:00:00 (时分秒固定为0)
    if (timeOption?.display_format === 'date') {
      return value.format('YYYY-MM-DD') + ' 00:00:00';
    }
    return value.format('YYYY-MM-DD HH:mm:ss');
  }
  return value;
};


export { TableFieldEditor, TagCascaderEditor };
