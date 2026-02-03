import { BUILD_IN_MODEL, CREDENTIAL_LIST } from '@/app/cmdb/constants/asset';
import { getSvgIcon } from './utils';
import dayjs from 'dayjs';
import { AttrFieldType } from '@/app/cmdb/types/assetManage';
import { Tag, Select, Input, InputNumber, DatePicker, Tooltip } from 'antd';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import GroupTreeSelector from '@/components/group-tree-select';
import { useUserInfoContext } from '@/context/userInfo';
import UserAvatar from '@/components/user-avatar';
import React from 'react';
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
} from '@/app/cmdb/types/assetManage';
import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';

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
const getOrganizationDisplayText = (value: any, flatGroups: Array<any>) => {
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
    // 表格中，用户字段为多选
    switch (attrType) {
      case 'user':
        return {
          ...columnItem,
          render: (_: unknown, record: any) => {
            const userIds = record[attrId];

            // 处理数组情况
            if (Array.isArray(userIds) && userIds.length > 0) {
              const userIdsStr = userIds.map((id: any) => String(id));
              const users = (config.userList || []).filter((user) =>
                userIdsStr.includes(String(user.id))
              );

              // 处理没有用户的情况
              if (users.length === 0) return <>--</>;

              return (
                <div className="flex items-center gap-2 max-h-[28px] overflow-hidden">
                  <UserAvatar key={users[0].id} userName={`${users[0].display_name}(${users[0].username})`} size="small" />
                  {users.length > 0 && (
                    <Tooltip
                      title={
                        <div className="flex flex-col gap-1">
                          {users.map((user) => (
                            <div key={user.id}>
                              {String(user.display_name || '')}({user.username})
                            </div>
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

            // 处理单个值情况
            if (userIds !== null && userIds !== undefined && userIds !== '') {
              const user = (config.userList || []).find(
                (item) => String(item.id) === String(userIds)
              );
              // 表格的user渲染
              return user ? <UserAvatar userName={`${user.display_name}(${user.username})`} /> : <>--</>;
            }

            // 处理空值情况
            return <>--</>;
          },
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
            const enumOptions = Array.isArray(item.option) ? item.option : [];
            return (
              <>
                {enumOptions.find((opt: EnumList) => opt.id === record[attrId])
                  ?.name || '--'}
              </>
            );
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
              )
            }

            return (
              <EllipsisWithTooltip
                className="whitespace-nowrap overflow-hidden text-ellipsis"
                text={record[attrId] || '--'}
              ></EllipsisWithTooltip>
            )
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
}) => {
  if (config.isEdit) {
    switch (config.fieldItem.attr_type) {
      case 'user':
        return (
          // 新增+编辑弹窗中，用户字段为多选
          <Select
            mode="multiple"
            showSearch
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
        const enumOpts = Array.isArray(config.fieldItem.option) ? config.fieldItem.option : [];
        return (
          <Select
            showSearch
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
          <Select>
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
        return <GroupTreeSelector multiple={true} />;
      case 'time':
        const timeOption = config.fieldItem.option as TimeAttrOption;
        const displayFormat = timeOption?.display_format || 'datetime';
        const showTime = displayFormat === 'datetime';
        const format =
          displayFormat === 'datetime' ? 'YYYY-MM-DD HH:mm:ss' : 'YYYY-MM-DD';
        return <DatePicker showTime={showTime} format={format} />;
      case 'int':
        return <InputNumber style={{ width: '100%' }} />;
      default:
        if (config.fieldItem.attr_type === 'str') {
          const strOption = config.fieldItem.option as StrAttrOption;
          if (strOption?.widget_type === 'multi_line') {
            return <Input.TextArea rows={4} />;
          }
        }
        return <Input />;
    }
  }
  switch (config.fieldItem.attr_type) {
    case 'user':
      // 实例详情页中的用户字段
      if (Array.isArray(config.value)) {
        if (config.value.length === 0) return '--';
        const userIds = config.value.map((id: any) => String(id));
        const users = (config.userList || []).filter((user) =>
          userIds.includes(String(user.id))
        );
        if (users.length === 0) return '--';
        const userNames = users
          .map((user) => `${user.display_name}(${user.username})`)
          .join('，');
        return config.hideUserAvatar ? (
          userNames
        ) : (
          <div className="flex items-center gap-2 flex-wrap">
            {users.map((user) => (
              <UserAvatar
                key={user.id}
                userName={`${user.display_name}(${user.username})`}
              />
            ))}
          </div>
        );
      }
      // 处理单选情况
      const user = (config.userList || []).find(
        (item) => String(item.id) === String(config.value)
      );
      if (!user) return '--';
      return config.hideUserAvatar ? (
        `${user.display_name}(${user.username})`
      ) : (
        <UserAvatar userName={`${user.display_name}(${user.username})`} />
      );
    case 'organization':
      return (
        <OrganizationField
          value={config.value}
          hideUserAvatar={config.hideUserAvatar}
        />
      );
    case 'bool':
      return config.value ? 'Yes' : 'No';
    case 'enum':
      const enumOptions = Array.isArray(config.fieldItem.option) ? config.fieldItem.option : [];
      if (Array.isArray(config.value)) {
        if (config.value.length === 0) return '--';
        const enumNames = config.value
          .map((val: any) => {
            return enumOptions.find(
              (item: EnumList) => item.id === val
            )?.name;
          })
          .filter((name) => name !== undefined)
          .join('，');
        return enumNames || '--';
      }
      return (
        enumOptions.find(
          (item: EnumList) => item.id === config.value,
        )?.name || '--'
      );
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
