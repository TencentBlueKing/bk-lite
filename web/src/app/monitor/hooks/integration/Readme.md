# 监控采集实例创建指南

本指南将以 Host 对象和 hostTelegraf 插件为例，说明如何创建一个新的监控采集实例。

## 1. 创建对象配置

首先在 `objects/os/host.tsx` 中创建对象配置文件。对象配置包含以下内容：

```typescript
export const useHostConfig = () => {
  const plugin = useHostTelegraf();

  // 注册插件
  const plugins = {
    Host: plugin, // key为插件名称，多个key代表同一个对象有多个插件
  };

  return {
    // 实例类型
    instance_type: 'os',

    // 仪表盘显示配置（目前已隐藏，备份方便后续拓展，值可以取[]）
    dashboardDisplay: [
      {
        indexId: 'env.procs', // 指标ID
        displayType: 'single', // 显示类型：single/dashboard/table/lineChart
        sortIndex: 0, // 排序
        displayDimension: [], // 显示维度
        style: {
          // 样式
          height: '200px',
          width: '15%',
        },
      },
      // ... 其他仪表盘配置
    ],

    // 视图表格中的关键指标显示配置
    tableDiaplay: [
      {
        type: 'progress', // 显示类型：progress/value/enum
        key: 'cpu_summary.usage', // 指标名称
      },
      // ... 其他关键指标
    ],

    // 创建监控策略中的指标查询唯一标识
    groupIds: {
      list: ['instance_id'],
      default: ['instance_id'],
    },

    // 注册的插件
    plugins,
    // ... 后续用到对象的配置信息可以添加在这里
  };
};
```

## 2. 创建插件配置

在 `plugins/os/hostTelegraf.tsx` 中创建插件配置文件。插件配置包含以下内容：

```typescript
export const useHostTelegraf = () => {
  const pluginConfig = {
    collect_type: 'host', // 采集类型
    config_type: ['cpu', 'disk'], // 配置类型
    collector: 'Telegraf', // 采集器
    instance_type: 'os', // 实例类型
    object_name: 'Host', // 对象名称
  };
  return {
    getPluginCfg: (extra) => {
      const pluginConfig = {
        // 自动配置模式
        auto: {
          formItems: [], // 表单项
          initTableItems: {}, // 表格初始项
          defaultForm: {}, // 默认表单值
          columns: [], // 表格列配置
          getParams: () => {}, // 获取请求参数方法
        },

        // 编辑模式
        edit: {
          formItems: [], // 表单项
          getDefaultForm: () => {}, // 获取默认表单值方法
          getParams: () => {}, // 获取请求参数的方法
        },

        // 手动配置模式（该功能暂时隐藏）
        manual: {
          defaultForm: {}, // 默认表单值
          formItems: [], // 表单项
          getParams: () => {}, // 获取请求参数的方法
          getConfigText: () => {}, // 获取生成的配置文本方法
        },
      };
      return {
        ...pluginConfig, // 公共的配置参数
        ...config[extra.mode], // 指定模式下的配置
      };
    },
  };
};
```

## 3. 注册对象到系统

在 `index.tsx` 中导入并注册对象：

```typescript
import { useHostConfig } from './objects/os/host';

export const useMonitorConfig = () => {
  const hostConfig = useHostConfig();

  const config = useMemo(
    () => ({
      Host: hostConfig,
      // ... 其他对象配置
    }),
    []
  );

  return {
    config, // 获取所有对象配置
    getPlugin, // 获取某个插件的配置信息
  };
};
```

## 4. 公共表单项管理

为了提高代码复用性和维护性，我们可以将公共的表单项配置抽离到 `common` 目录下。以 Host 对象为例：

### 4.1 创建公共表单配置

在 `common/hostFormItems.tsx` 中创建：

```typescript
export const useHostFormItems = () => {
  const { t } = useTranslation();

  return {
    // 获取公共表单项，支持禁用配置
    getCommonFormItems: (disabledFormItems: Record<string, boolean> = {}) => {
      return (
        <>
          <Form.Item
            label={t('monitor.intergrations.metricType')}
            name="metric_type"
            rules={[{ required: true }]}
          >
            <Checkbox.Group disabled={disabledFormItems.metric_type}>
              <Space direction="vertical">
                <Checkbox value="cpu">CPU</Checkbox>
                <Checkbox value="disk">Disk</Checkbox>
                {/* ... 其他指标类型 */}
              </Space>
            </Checkbox.Group>
          </Form.Item>
        </>
      );
    },

    // 可以添加其他公共表单项方法
    getAdvancedFormItems: () => {
      // 高级配置表单项
    },
  };
};
```

### 4.2 在插件中使用公共表单

在插件配置中引用公共表单：

```typescript
import { useHostFormItems } from '../../common/hostFormItems';

export const useHostTelegraf = () => {
  const hostFormItems = useHostFormItems();

  return {
    getPluginCfg: (extra) => {
      const config = {
        auto: {
          // 自动配置使用公共表单
          formItems: hostFormItems.getCommonFormItems(),
          // ... 其他配置
        },

        edit: {
          // 编辑模式使用公共表单，并禁用某些项
          formItems: hostFormItems.getCommonFormItems({
            metric_type: true,
          }),
          // ... 其他配置
        },

        manual: {
          // 手动配置使用公共表单
          formItems: hostFormItems.getCommonFormItems(),
          // ... 其他配置
        },
      };
      return {
        // ...公共的配置参数
        ...config[extra.mode], // 指定模式下的配置
      };
    },
  };
};
```

### 4.3 公共表单项的优点

1. **代码复用**：避免在不同模式下重复编写相同的表单配置
2. **统一维护**：表单项的修改只需要在一处进行
3. **配置灵活**：支持通过参数控制表单项的禁用状态
4. **类型统一**：确保不同模式下表单项的一致性

### 最佳实践

1. 将同一对象的公共表单项放在一个文件中管理
2. 按功能划分不同的获取方法（如基础配置、高级配置等）
3. 提供配置项来控制表单项的状态
4. 使用 TypeScript 类型来规范表单数据结构
5. 配置项的命名要见名知意，便于维护

完整的目录结构如下：

```
src/app/monitor/hooks/intergration/
├── common/
│   ├── hostFormItems.tsx           # Host对象的公共表单配置
│   ├── databaseFormItems.tsx       # 数据库类的公共表单配置
│   └── networkDeviceFormItems.tsx  # 网络设备的公共表单配置
├── objects/
│   └── os/
│       └── host.tsx               # Host对象配置
├── plugins/
│   └── os/
│       └── hostTelegraf.tsx      # Host插件配置
└── index.tsx                     # 配置入口文件
```

## 配置说明

### 对象配置

- `instance_type`: 实例类型，用于标识对象类型
- `dashboardDisplay`: 仪表盘显示配置，包含多个面板的显示设置（目前已隐藏）
- `tableDiaplay`: 表格显示配置，定义在列表中显示的关键指标
- `groupIds`: 指标唯一标识配置，定义监控策略中指标的唯一标识
- `plugins`: 注册到该对象的插件列表

### 插件配置

- `collect_type`: 采集类型，如 host/mysql/redis 等
- `config_type`: 配置类型列表，定义支持的采集指标
- `collector`: 采集器名称，如 Telegraf
- `instance_type`: 实例类型，需要与对象配置匹配
- `object_name`: 对象名称
- `formItems`: 表单配置项，定义配置界面的表单
- `getParams`: 请求参数处理方法，处理请求数据
- `getConfigText`: 配置文本生成方法，生成采集配置

### 模式说明

- `auto`: 自动配置模式，用于批量配置场景
- `edit`: 编辑模式，用于修改现有配置
- `manual`: 手动配置模式，用于单个实例配置，（目前已隐藏）
