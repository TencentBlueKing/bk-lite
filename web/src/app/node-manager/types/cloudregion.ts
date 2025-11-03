import type { TableDataItem } from '@/app/node-manager/types/index';
import { ListItem } from '@/types';
import { ColumnFilterItem } from 'antd/es/table/interface';

//通用基础实体接口
interface BaseEntity {
  id: string;
  name: string;
}

//带描述的基础实体
interface BaseEntityWithDescription extends BaseEntity {
  description: string;
}

//配置页面的table的列定义
interface ConfigHookParams {
  openSub: (key: string, item?: any) => void;
  nodeClick: () => void;
  modifyDeleteconfirm: (key: string) => void;
  applyConfigurationClick: (item: TableDataItem) => void;
  filter: ColumnFilterItem[];
}
// 子配置页面table的列定义
interface SubConfigHookParams {
  edit: (item: ConfigListProps) => void;
  nodeData: ConfigData;
}
interface VariableProps {
  openUerModal: (type: string, form: TableDataItem) => void;
  getFormDataById: (key: string) => TableDataItem;
  delConfirm: (key: string, text: any) => void;
}

//基础配置项接口
interface BaseConfigItem extends BaseEntity {
  collector_id?: string;
  collector_name?: string;
  operating_system: string;
  node_count: string | number;
  config_template?: string;
  nodes?: string[];
}

//API返回的配置文件列表的类型
interface ConfigListProps extends BaseConfigItem {
  collector?: string;
}

//页面展示用的配置数据类型（将API数据转换为页面需要的格式）
interface ConfigData
  extends Omit<
    BaseConfigItem,
    | 'id'
    | 'operating_system'
    | 'node_count'
    | 'config_template'
    | 'collector_name'
  > {
  key: string;
  collector?: string;
  operatingSystem: string;
  nodeCount: number;
  configInfo: string;
  nodesList?: ListItem;
  operating_system?: string;
  collector_name?: string;
}

//后端返回的采集器列表
interface CollectorItem {
  id?: string;
  collector_id?: string;
  collector_name?: string;
  configuration_id?: string;
  configuration_name?: string;
  message?: string;
  status?: number;
}

//node展开的数据类型
interface NodeExpandData {
  key: string;
  name: string;
  filename: string;
  status: number;
  nodeid: string;
}

//更新配置文件的请求
interface UpdateConfigReq {
  node_ids: string[];
  collector_configuration_id: string;
}

//节点基础信息
interface BaseNodeInfo extends BaseEntity {
  ip: string;
  operating_system: string;
}

//节点模块API返回的数据
interface NodeItemRes extends BaseNodeInfo {
  status: {
    status: string | number;
  };
  [key: string]: any;
}

//节点页面展示用的数据格式
interface MappedNodeItem extends Omit<BaseNodeInfo, 'id' | 'operating_system'> {
  key: string;
  operatingSystem: string;
  sidecar: string;
}

//控制器安装时的节点数据
interface NodeItem extends Pick<BaseNodeInfo, 'ip'> {
  id?: string;
  os: string;
  organizations?: string[];
  username?: string;
  password?: string;
  port?: number;
}

interface SubRef {
  getChildConfig: () => void;
}

interface SubProps {
  cancel: () => void;
  edit: (item: ConfigListProps) => void;
  nodeData: ConfigData;
  collectors: TableDataItem[];
}

interface CloudRegionItem extends BaseEntityWithDescription {
  icon: string;
}

interface VarSourceItem extends Omit<BaseEntityWithDescription, 'id'> {
  key: string;
}

interface VarResItem extends BaseEntity {
  key: string;
  value: string;
  description: string;
}

interface CloudRegionCardProps extends Omit<BaseEntity, 'id'> {
  id: number;
  introduction: string;
  [key: string]: any;
}

interface ControllerInstallFields {
  id?: number;
  cloud_region_id: number;
  nodes: NodeItem[];
  work_node?: string;
  sidecar_package?: string;
  executor_package?: string;
}

interface ControllerInstallProps {
  cancel: () => void;
  config?: any;
}

interface ConfigParams {
  name: string;
  collector_id: string;
  cloud_region_id?: number;
  config_template: string;
  nodes?: string[];
}

interface ConfigListParams {
  cloud_region_id?: number;
  name?: string;
  node_id?: string;
  ids?: string[];
}

export type {
  BaseEntity,
  BaseEntityWithDescription,
  BaseConfigItem,
  BaseNodeInfo,
  ConfigHookParams,
  VariableProps,
  ConfigListProps,
  CollectorItem,
  NodeExpandData,
  UpdateConfigReq,
  NodeItemRes,
  MappedNodeItem,
  ConfigData,
  SubRef,
  SubProps,
  CloudRegionItem,
  VarSourceItem,
  VarResItem,
  CloudRegionCardProps,
  ControllerInstallFields,
  ControllerInstallProps,
  NodeItem,
  SubConfigHookParams,
  ConfigParams,
  ConfigListParams,
};
