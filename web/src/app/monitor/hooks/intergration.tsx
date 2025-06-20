import React, { useMemo } from 'react';
import { Form, Checkbox, Space, Select, Input, InputNumber } from 'antd';
import Password from '@/app/monitor/components/password';
import { useTranslation } from '@/utils/i18n';
import { getConfigByPluginName } from '@/app/monitor/utils/common';
import {
  TIMEOUT_UNITS,
  useMiddleWareFields,
} from '@/app/monitor/constants/monitor';
import PermissionWrapper from '@/components/permission';
import type { MenuProps } from 'antd';
const { Option } = Select;

interface UseColumnsAndFormItemsParams {
  pluginName: string;
  collectType: string;
  columns: any[];
  mode?: string;
}

const useColumnsAndFormItems = ({
  collectType,
  pluginName,
  columns,
}: UseColumnsAndFormItemsParams) => {
  const { t } = useTranslation();

  const result = useMemo(() => {
    switch (collectType) {
      case 'host':
        return {
          displaycolumns: [columns[0], ...columns.slice(4, 7)],
          formItems: (
            <Form.Item
              label={t('monitor.intergrations.metricType')}
              name="metric_type"
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                },
              ]}
            >
              <Checkbox.Group>
                <Space direction="vertical">
                  <Checkbox value="cpu">
                    <span>
                      <span className="w-[80px] inline-block">CPU</span>
                      <span className="text-[var(--color-text-3)] text-[12px]">
                        {t('monitor.intergrations.cpuDes')}
                      </span>
                    </span>
                  </Checkbox>
                  <Checkbox value="disk">
                    <span>
                      <span className="w-[80px] inline-block">Disk</span>
                      <span className="text-[var(--color-text-3)] text-[12px]">
                        {t('monitor.intergrations.diskDes')}
                      </span>
                    </span>
                  </Checkbox>
                  <Checkbox value="diskio">
                    <span>
                      <span className="w-[80px] inline-block">Disk IO</span>
                      <span className="text-[var(--color-text-3)] text-[12px]">
                        {t('monitor.intergrations.diskIoDes')}
                      </span>
                    </span>
                  </Checkbox>
                  <Checkbox value="mem">
                    <span>
                      <span className="w-[80px] inline-block">Memory</span>
                      <span className="text-[var(--color-text-3)] text-[12px]">
                        {t('monitor.intergrations.memoryDes')}
                      </span>
                    </span>
                  </Checkbox>
                  <Checkbox value="net">
                    <span>
                      <span className="w-[80px] inline-block">Net</span>
                      <span className="text-[var(--color-text-3)] text-[12px]">
                        {t('monitor.intergrations.netDes')}
                      </span>
                    </span>
                  </Checkbox>
                  <Checkbox value="processes">
                    <span>
                      <span className="w-[80px] inline-block">Processes</span>
                      <span className="text-[var(--color-text-3)] text-[12px]">
                        {t('monitor.intergrations.processesDes')}
                      </span>
                    </span>
                  </Checkbox>
                  <Checkbox value="system">
                    <span>
                      <span className="w-[80px] inline-block">System</span>
                      <span className="text-[var(--color-text-3)] text-[12px]">
                        {t('monitor.intergrations.systemDes')}
                      </span>
                    </span>
                  </Checkbox>
                  <Checkbox value="gpu">
                    <span>
                      <span className="w-[80px] inline-block">Nvidia-GPU</span>
                      <span className="text-[var(--color-text-3)] text-[12px]">
                        {t('monitor.intergrations.gpuDes')}
                      </span>
                    </span>
                  </Checkbox>
                </Space>
              </Checkbox.Group>
            </Form.Item>
          ),
        };
      case 'trap':
        return {
          displaycolumns: [columns[0], ...columns.slice(4, 7)],
          formItems: null,
        };
      case 'web':
        return {
          displaycolumns: [columns[1], ...columns.slice(3, 7)],
          formItems: null,
        };
      case 'ping':
        return {
          displaycolumns: [columns[1], ...columns.slice(3, 7)],
          formItems: null,
        };
      case 'snmp':
        return {
          displaycolumns: [columns[0], columns[2], ...columns.slice(4, 7)],
          formItems: (
            <>
              <Form.Item required label={t('monitor.intergrations.port')}>
                <Form.Item
                  noStyle
                  name="port"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <InputNumber
                    className="w-[300px] mr-[10px]"
                    min={1}
                    precision={0}
                  />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.portDes')}
                </span>
              </Form.Item>
              <Form.Item required label={t('monitor.intergrations.version')}>
                <Form.Item
                  noStyle
                  name="version"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Select
                    showSearch
                    className="mr-[10px]"
                    style={{ width: '300px' }}
                  >
                    <Option value={2}>v2c</Option>
                    <Option value={3}>v3</Option>
                  </Select>
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.versionDes')}
                </span>
              </Form.Item>
              <Form.Item
                noStyle
                shouldUpdate={(prevValues, currentValues) =>
                  prevValues.version !== currentValues.version
                }
              >
                {({ getFieldValue }) =>
                  getFieldValue('version') === 2 ? (
                    <Form.Item
                      required
                      label={t('monitor.intergrations.community')}
                    >
                      <Form.Item
                        noStyle
                        name="community"
                        rules={[
                          {
                            required: true,
                            message: t('common.required'),
                          },
                        ]}
                      >
                        <Input className="w-[300px] mr-[10px]" />
                      </Form.Item>
                      <span className="text-[12px] text-[var(--color-text-3)]">
                        {t('monitor.intergrations.communityDes')}
                      </span>
                    </Form.Item>
                  ) : (
                    <>
                      <Form.Item required label={t('common.name')}>
                        <Form.Item
                          noStyle
                          name="sec_name"
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <Input className="w-[300px] mr-[10px]" />
                        </Form.Item>
                        <span className="text-[12px] text-[var(--color-text-3)]">
                          {t('monitor.intergrations.nameDes')}
                        </span>
                      </Form.Item>
                      <Form.Item required label={t('monitor.events.level')}>
                        <Form.Item
                          noStyle
                          name="sec_level"
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <Select
                            showSearch
                            className="mr-[10px]"
                            style={{ width: '300px' }}
                          >
                            <Option value="noAuthNoPriv">noAuthNoPriv</Option>
                            <Option value="authNoPriv">authNoPriv</Option>
                            <Option value="authPriv">authPriv</Option>
                          </Select>
                        </Form.Item>
                        <span className="text-[12px] text-[var(--color-text-3)]">
                          {t('monitor.intergrations.levelDes')}
                        </span>
                      </Form.Item>
                      <Form.Item
                        required
                        label={t('monitor.intergrations.authProtocol')}
                      >
                        <Form.Item
                          noStyle
                          name="auth_protocol"
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <Input className="w-[300px] mr-[10px]" />
                        </Form.Item>
                        <span className="text-[12px] text-[var(--color-text-3)]">
                          {t('monitor.intergrations.authProtocolDes')}
                        </span>
                      </Form.Item>
                      <Form.Item
                        required
                        label={t('monitor.intergrations.authPassword')}
                      >
                        <Form.Item
                          noStyle
                          name="auth_password"
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <Password className="w-[300px] mr-[10px]" />
                        </Form.Item>
                        <span className="text-[12px] text-[var(--color-text-3)]">
                          {t('monitor.intergrations.authPasswordDes')}
                        </span>
                      </Form.Item>
                      <Form.Item
                        required
                        label={t('monitor.intergrations.privProtocol')}
                      >
                        <Form.Item
                          noStyle
                          name="priv_protocol"
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <Input className="w-[300px] mr-[10px]" />
                        </Form.Item>
                        <span className="text-[12px] text-[var(--color-text-3)]">
                          {t('monitor.intergrations.privProtocolDes')}
                        </span>
                      </Form.Item>
                      <Form.Item
                        required
                        label={t('monitor.intergrations.privPassword')}
                      >
                        <Form.Item
                          noStyle
                          name="priv_password"
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <Password className="w-[300px] mr-[10px]" />
                        </Form.Item>
                        <span className="text-[12px] text-[var(--color-text-3)]">
                          {t('monitor.intergrations.privPasswordDes')}
                        </span>
                      </Form.Item>
                    </>
                  )
                }
              </Form.Item>
              <Form.Item required label={t('monitor.intergrations.timeout')}>
                <Form.Item
                  noStyle
                  name="timeout"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <InputNumber
                    className="mr-[10px]"
                    min={1}
                    precision={0}
                    addonAfter={
                      <Select style={{ width: 116 }} defaultValue="s">
                        {TIMEOUT_UNITS.map((item: string) => (
                          <Option key={item} value={item}>
                            {item}
                          </Option>
                        ))}
                      </Select>
                    }
                  />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.timeoutDes')}
                </span>
              </Form.Item>
            </>
          ),
        };
      case 'ipmi':
        return {
          displaycolumns: [columns[0], columns[2], ...columns.slice(4, 7)],
          formItems: (
            <>
              <Form.Item label={t('monitor.intergrations.username')} required>
                <Form.Item
                  noStyle
                  name="username"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.usernameDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.password')} required>
                <Form.Item
                  noStyle
                  name="password"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Password className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.passwordDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.protocol')} required>
                <Form.Item
                  noStyle
                  name="protocol"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.protocolDes')}
                </span>
              </Form.Item>
            </>
          ),
        };
      case 'middleware':
        return {
          displaycolumns: [columns[0], ...columns.slice(3, 7)],
          formItems: (
            <>
              {['RabbitMQ', 'ActiveMQ', 'Tomcat'].includes(pluginName) && (
                <>
                  <Form.Item
                    label={t('monitor.intergrations.username')}
                    required
                  >
                    <Form.Item
                      noStyle
                      name="username"
                      rules={[
                        {
                          required: true,
                          message: t('common.required'),
                        },
                      ]}
                    >
                      <Input className="w-[300px] mr-[10px]" />
                    </Form.Item>
                    <span className="text-[12px] text-[var(--color-text-3)]">
                      {t('monitor.intergrations.usernameDes')}
                    </span>
                  </Form.Item>
                  <Form.Item
                    label={t('monitor.intergrations.password')}
                    required
                  >
                    <Form.Item
                      noStyle
                      name="password"
                      rules={[
                        {
                          required: true,
                          message: t('common.required'),
                        },
                      ]}
                    >
                      <Password className="w-[300px] mr-[10px]" />
                    </Form.Item>
                    <span className="text-[12px] text-[var(--color-text-3)]">
                      {t('monitor.intergrations.passwordDes')}
                    </span>
                  </Form.Item>
                </>
              )}
              {pluginName === 'Zookeeper' && (
                <Form.Item required label={t('monitor.intergrations.timeout')}>
                  <Form.Item
                    noStyle
                    name="timeout"
                    rules={[
                      {
                        required: true,
                        message: t('common.required'),
                      },
                    ]}
                  >
                    <InputNumber
                      className="mr-[10px]"
                      min={1}
                      precision={0}
                      addonAfter={
                        <Select style={{ width: 116 }} defaultValue="s">
                          {TIMEOUT_UNITS.map((item: string) => (
                            <Option key={item} value={item}>
                              {item}
                            </Option>
                          ))}
                        </Select>
                      }
                    />
                  </Form.Item>
                  <span className="text-[12px] text-[var(--color-text-3)]">
                    {t('monitor.intergrations.timeoutDes')}
                  </span>
                </Form.Item>
              )}
            </>
          ),
        };
      case 'docker':
        return {
          displaycolumns: [columns[0], columns[7], ...columns.slice(4, 7)],
          formItems: null,
        };
      case 'database':
        const isUsernameAndPasswordRequired = !['Redis', 'MongoDB'].includes(
          pluginName
        );
        return {
          displaycolumns:
            pluginName === 'ElasticSearch'
              ? [columns[0], columns[8], ...columns.slice(4, 7)]
              : [columns[0], columns[9], columns[10], ...columns.slice(4, 7)],
          formItems: (
            <>
              <Form.Item
                label={t('monitor.intergrations.username')}
                required={isUsernameAndPasswordRequired}
              >
                <Form.Item
                  noStyle
                  name="username"
                  rules={[
                    {
                      required: isUsernameAndPasswordRequired,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.usernameDes')}
                </span>
              </Form.Item>
              <Form.Item
                label={t('monitor.intergrations.password')}
                required={isUsernameAndPasswordRequired}
              >
                <Form.Item
                  noStyle
                  name="password"
                  rules={[
                    {
                      required: isUsernameAndPasswordRequired,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Password className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.passwordDes')}
                </span>
              </Form.Item>
            </>
          ),
        };
      case 'http':
        const httpColumns =
          pluginName === 'VMWare'
            ? [columns[0], columns[11], ...columns.slice(4, 7)]
            : [columns[0], ...columns.slice(4, 7)];
        return {
          displaycolumns: httpColumns,
          formItems: (
            <>
              <Form.Item label={t('monitor.intergrations.username')} required>
                <Form.Item
                  noStyle
                  name="username"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.usernameDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.password')} required>
                <Form.Item
                  noStyle
                  name="password"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Password className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.passwordDes')}
                </span>
              </Form.Item>
            </>
          ),
        };
      case 'jmx':
        return {
          displaycolumns: [
            columns[0],
            columns[12],
            columns[13],
            ...columns.slice(4, 7),
          ],
          formItems: (
            <>
              <Form.Item label={t('monitor.intergrations.username')}>
                <Form.Item noStyle name="username">
                  <Input className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.usernameDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.password')}>
                <Form.Item noStyle name="password">
                  <Password className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.passwordDes')}
                </span>
              </Form.Item>
            </>
          ),
        };
      case 'exporter':
        return {
          displaycolumns: [
            columns[0],
            ...columns.slice(13, 16),
            ...columns.slice(4, 7),
          ],
          formItems: (
            <>
              <Form.Item label={t('monitor.intergrations.username')} required>
                <Form.Item
                  noStyle
                  name="ENV_USER"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.usernameDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.password')} required>
                <Form.Item
                  noStyle
                  name="ENV_PASSWORD"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Password className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.passwordDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.seviceName')} required>
                <Form.Item
                  noStyle
                  name="ENV_SERVICE_NAME"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.seviceNameDes')}
                </span>
              </Form.Item>
            </>
          ),
        };
      case 'bkpull':
        return {
          displaycolumns: [
            columns[0],
            ...columns.slice(9, 11),
            ...columns.slice(4, 7),
          ],
          formItems: null,
        };
      default:
        return {
          displaycolumns: [columns[0], ...columns.slice(3, 7)],
          formItems: null,
        };
    }
  }, [collectType, columns, t]);

  return result;
};

const useFormItems = ({
  pluginName,
  collectType,
  mode,
}: UseColumnsAndFormItemsParams) => {
  const { t } = useTranslation();
  const middleWareFieldsMap = useMiddleWareFields();
  const isEdit = mode === 'edit';

  const result = useMemo(() => {
    switch (collectType) {
      case 'host':
        return {
          formItems: (
            <>
              <Form.Item
                label={t('monitor.intergrations.metricType')}
                name="metric_type"
                rules={[
                  {
                    required: true,
                    message: t('common.required'),
                  },
                ]}
              >
                <Checkbox.Group disabled={isEdit}>
                  <Space direction="vertical">
                    <Checkbox value="cpu">
                      <span>
                        <span className="w-[80px] inline-block">CPU</span>
                        <span className="text-[var(--color-text-3)] text-[12px]">
                          {t('monitor.intergrations.cpuDes')}
                        </span>
                      </span>
                    </Checkbox>
                    <Checkbox value="disk">
                      <span>
                        <span className="w-[80px] inline-block">Disk</span>
                        <span className="text-[var(--color-text-3)] text-[12px]">
                          {t('monitor.intergrations.diskDes')}
                        </span>
                      </span>
                    </Checkbox>
                    <Checkbox value="diskio">
                      <span>
                        <span className="w-[80px] inline-block">Disk IO</span>
                        <span className="text-[var(--color-text-3)] text-[12px]">
                          {t('monitor.intergrations.diskIoDes')}
                        </span>
                      </span>
                    </Checkbox>
                    <Checkbox value="mem">
                      <span>
                        <span className="w-[80px] inline-block">Memory</span>
                        <span className="text-[var(--color-text-3)] text-[12px]">
                          {t('monitor.intergrations.memoryDes')}
                        </span>
                      </span>
                    </Checkbox>
                    <Checkbox value="net">
                      <span>
                        <span className="w-[80px] inline-block">Net</span>
                        <span className="text-[var(--color-text-3)] text-[12px]">
                          {t('monitor.intergrations.netDes')}
                        </span>
                      </span>
                    </Checkbox>
                    <Checkbox value="processes">
                      <span>
                        <span className="w-[80px] inline-block">Processes</span>
                        <span className="text-[var(--color-text-3)] text-[12px]">
                          {t('monitor.intergrations.processesDes')}
                        </span>
                      </span>
                    </Checkbox>
                    <Checkbox value="system">
                      <span>
                        <span className="w-[80px] inline-block">System</span>
                        <span className="text-[var(--color-text-3)] text-[12px]">
                          {t('monitor.intergrations.systemDes')}
                        </span>
                      </span>
                    </Checkbox>
                    <Checkbox value="gpu">
                      <span>
                        <span className="w-[80px] inline-block">
                          Nvidia-GPU
                        </span>
                        <span className="text-[var(--color-text-3)] text-[12px]">
                          {t('monitor.intergrations.gpuDes')}
                        </span>
                      </span>
                    </Checkbox>
                  </Space>
                </Checkbox.Group>
              </Form.Item>
              <Form.Item required label="IP">
                <Form.Item
                  noStyle
                  name="monitor_ip"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.ipDes')}
                </span>
              </Form.Item>
            </>
          ),
          configText: {
            cpu: `[[inputs.cpu]]
    percpu = true
    totalcpu = true
    collect_cpu_time = false
    report_active = false
    core_tags = false
    interval = "$intervals"
    tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="cpu" }
    
`,
            disk: `[[inputs.disk]]
    ignore_fs = ["tmpfs", "devtmpfs", "devfs", "iso9660", "overlay", "aufs", "squashfs"]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="disk" }
    
`,
            diskio: `[[inputs.diskio]]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="diskio" }
    
`,
            mem: `[[inputs.mem]]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="mem" }
    
`,
            net: `[[inputs.net]]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="net" }

`,
            processes: `[[inputs.processes]]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="processes" }
    
`,
            system: `[[inputs.system]]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id","instance_type"="os","collect_type"="host","config_type"="system" }
    
`,
            gpu: `[[inputs.nvidia_smi]]
    interval = "$intervals"
    [inputs.docker.tags]
        instance_id = "$instance_id"
        instance_type = "os"
        collect_type = "host"
        config_type = "gpu"
    
`,
          },
        };
      case 'trap':
        return {
          formItems: (
            <Form.Item required label="IP">
              <Form.Item
                noStyle
                name="monitor_ip"
                rules={[
                  {
                    required: true,
                    message: t('common.required'),
                  },
                ]}
              >
                <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
              </Form.Item>
              <span className="text-[12px] text-[var(--color-text-3)]">
                {t('monitor.intergrations.ipDes')}
              </span>
            </Form.Item>
          ),
          configText: `[[inputs.$config_type]]
          interval = "$intervals"
          tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
        };
      case 'web':
        return {
          formItems: (
            <Form.Item required label="URL">
              <Form.Item
                noStyle
                name="monitor_url"
                rules={[
                  {
                    required: true,
                    message: t('common.required'),
                  },
                ]}
              >
                <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
              </Form.Item>
              <span className="text-[12px] text-[var(--color-text-3)]">
                {t('monitor.intergrations.urlDes')}
              </span>
            </Form.Item>
          ),
          configText: `[[inputs.$config_type]]
    urls = ["$monitor_url"]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id","instance_type"="$instance_type","collect_type"="$collect_type" }`,
        };
      case 'ping':
        return {
          formItems: (
            <Form.Item required label="URL">
              <Form.Item
                noStyle
                name="monitor_url"
                rules={[
                  {
                    required: true,
                    message: t('common.required'),
                  },
                ]}
              >
                <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
              </Form.Item>
              <span className="text-[12px] text-[var(--color-text-3)]">
                {t('monitor.intergrations.urlDes')}
              </span>
            </Form.Item>
          ),
          configText: `[[inputs.$config_type]]
          urls = ["$monitor_url"]
          interval = "$intervals"
          tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
        };
      case 'snmp':
        return {
          formItems: (
            <>
              <Form.Item required label="IP">
                <Form.Item
                  noStyle
                  name="monitor_ip"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.ipDes')}
                </span>
              </Form.Item>
              <Form.Item required label={t('monitor.intergrations.port')}>
                <Form.Item
                  noStyle
                  name="port"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <InputNumber
                    className="w-[300px] mr-[10px]"
                    min={1}
                    precision={0}
                    disabled={isEdit}
                  />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.portDes')}
                </span>
              </Form.Item>
              <Form.Item required label={t('monitor.intergrations.version')}>
                <Form.Item
                  noStyle
                  name="version"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Select
                    className="mr-[10px]"
                    style={{ width: '300px' }}
                    disabled={isEdit}
                    showSearch
                  >
                    <Option value={2}>v2c</Option>
                    <Option value={3}>v3</Option>
                  </Select>
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.versionDes')}
                </span>
              </Form.Item>
              <Form.Item
                noStyle
                shouldUpdate={(prevValues, currentValues) =>
                  prevValues.version !== currentValues.version
                }
              >
                {({ getFieldValue }) =>
                  getFieldValue('version') === 2 ? (
                    <Form.Item
                      required
                      label={t('monitor.intergrations.community')}
                    >
                      <Form.Item
                        noStyle
                        name="community"
                        rules={[
                          {
                            required: true,
                            message: t('common.required'),
                          },
                        ]}
                      >
                        <Input className="w-[300px] mr-[10px]" />
                      </Form.Item>
                      <span className="text-[12px] text-[var(--color-text-3)]">
                        {t('monitor.intergrations.communityDes')}
                      </span>
                    </Form.Item>
                  ) : (
                    <>
                      <Form.Item required label={t('common.name')}>
                        <Form.Item
                          noStyle
                          name="sec_name"
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <Input className="w-[300px] mr-[10px]" />
                        </Form.Item>
                        <span className="text-[12px] text-[var(--color-text-3)]">
                          {t('monitor.intergrations.nameDes')}
                        </span>
                      </Form.Item>
                      <Form.Item required label={t('monitor.events.level')}>
                        <Form.Item
                          noStyle
                          name="sec_level"
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <Select
                            className="mr-[10px]"
                            style={{ width: '300px' }}
                            showSearch
                          >
                            <Option value="noAuthNoPriv">noAuthNoPriv</Option>
                            <Option value="authNoPriv">authNoPriv</Option>
                            <Option value="authPriv">authPriv</Option>
                          </Select>
                        </Form.Item>
                        <span className="text-[12px] text-[var(--color-text-3)]">
                          {t('monitor.intergrations.levelDes')}
                        </span>
                      </Form.Item>
                      <Form.Item
                        required
                        label={t('monitor.intergrations.authProtocol')}
                      >
                        <Form.Item
                          noStyle
                          name="auth_protocol"
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <Input className="w-[300px] mr-[10px]" />
                        </Form.Item>
                        <span className="text-[12px] text-[var(--color-text-3)]">
                          {t('monitor.intergrations.authProtocolDes')}
                        </span>
                      </Form.Item>
                      <Form.Item
                        required
                        label={t('monitor.intergrations.authPassword')}
                      >
                        <Form.Item
                          noStyle
                          name="auth_password"
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <Password
                            className="w-[300px] mr-[10px]"
                            disabled={isEdit}
                          />
                        </Form.Item>
                        <span className="text-[12px] text-[var(--color-text-3)]">
                          {t('monitor.intergrations.authPasswordDes')}
                        </span>
                      </Form.Item>
                      <Form.Item
                        required
                        label={t('monitor.intergrations.privProtocol')}
                      >
                        <Form.Item
                          noStyle
                          name="priv_protocol"
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <Input className="w-[300px] mr-[10px]" />
                        </Form.Item>
                        <span className="text-[12px] text-[var(--color-text-3)]">
                          {t('monitor.intergrations.privProtocolDes')}
                        </span>
                      </Form.Item>
                      <Form.Item
                        required
                        label={t('monitor.intergrations.privPassword')}
                      >
                        <Form.Item
                          noStyle
                          name="priv_password"
                          rules={[
                            {
                              required: true,
                              message: t('common.required'),
                            },
                          ]}
                        >
                          <Password
                            className="w-[300px] mr-[10px]"
                            disabled={isEdit}
                          />
                        </Form.Item>
                        <span className="text-[12px] text-[var(--color-text-3)]">
                          {t('monitor.intergrations.privPasswordDes')}
                        </span>
                      </Form.Item>
                    </>
                  )
                }
              </Form.Item>
              <Form.Item required label={t('monitor.intergrations.timeout')}>
                <Form.Item
                  noStyle
                  name="timeout"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <InputNumber
                    className="mr-[10px]"
                    min={1}
                    precision={0}
                    addonAfter={
                      <Select style={{ width: 116 }} defaultValue="s">
                        {TIMEOUT_UNITS.map((item: string) => (
                          <Option key={item} value={item}>
                            {item}
                          </Option>
                        ))}
                      </Select>
                    }
                  />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.timeoutDes')}
                </span>
              </Form.Item>
            </>
          ),
          configText: {
            v2: `[[inputs.snmp]]
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }
    agents = ["udp://$monitor_ip:$port"]
    version = $version
    community= "$community"
    interval = "$intervals"
    timeout = "$timeouts" 

    [[inputs.snmp.field]]
        oid = "RFC1213-MIB::sysUpTime.0"
        name = "uptime"

    [[inputs.snmp.field]]
        oid = "RFC1213-MIB::sysName.0"
        name = "source"
        is_tag = true

    [[inputs.snmp.table]]
        oid = "IF-MIB::ifTable"
        name = "interface"
        inherit_tags = ["source"]

    [[inputs.snmp.table.field]]
        oid = "IF-MIB::ifDescr"
        name = "ifDescr"
        is_tag = true`,
            v3: `[[inputs.snmp]]
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="snmp" }
    agents =["udp://$monitor_ip:$port"]
    version = $version
    timeout = "$timeouts" 

    sec_name = "$sec_name"
    sec_level = "$sec_level"
    auth_protocol = "$auth_protocol"
    auth_password = "$auth_password"
    priv_protocol = "$priv_protocol"
    priv_password = "$priv_password"

    [[inputs.snmp.field]]
        oid = "RFC1213-MIB::sysUpTime.0"
        name = "uptime"

    [[inputs.snmp.field]]
        oid = "RFC1213-MIB::sysName.0"
        name = "source"
        is_tag = true

    [[inputs.snmp.table]]
        oid = "IF-MIB::ifTable"
        name = "interface"
        inherit_tags = ["source"]

    [[inputs.snmp.table.field]]
        oid = "IF-MIB::ifDescr"
        name = "ifDescr"
        is_tag = true`,
          },
        };
      case 'ipmi':
        return {
          formItems: (
            <>
              <Form.Item required label="IP">
                <Form.Item
                  noStyle
                  name="monitor_ip"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.ipDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.username')} required>
                <Form.Item
                  noStyle
                  name="username"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.usernameDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.password')} required>
                <Form.Item
                  noStyle
                  name="password"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Password className="w-[300px] mr-[10px]" disabled={isEdit} />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.passwordDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.protocol')} required>
                <Form.Item
                  noStyle
                  name="protocol"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input
                    readOnly
                    disabled={isEdit}
                    className="w-[300px] mr-[10px]"
                  />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.protocolDes')}
                </span>
              </Form.Item>
            </>
          ),
          configText: `[[inputs.ipmi_sensor]]
    servers = ["$username:$password@lanplus($monitor_ip)"]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
        };
      case 'middleware':
        return {
          formItems: (
            <>
              <Form.Item
                required
                label={
                  middleWareFieldsMap[pluginName] || middleWareFieldsMap.default
                }
              >
                <Form.Item
                  noStyle
                  name="monitor_url"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {middleWareFieldsMap[`${pluginName}Des`] ||
                    middleWareFieldsMap.defaultDes}
                </span>
              </Form.Item>
              {pluginName === 'Zookeeper' && (
                <Form.Item required label={t('monitor.intergrations.timeout')}>
                  <Form.Item
                    noStyle
                    name="timeout"
                    rules={[
                      {
                        required: true,
                        message: t('common.required'),
                      },
                    ]}
                  >
                    <InputNumber
                      className="mr-[10px]"
                      min={1}
                      precision={0}
                      addonAfter={
                        <Select style={{ width: 116 }} defaultValue="s">
                          {TIMEOUT_UNITS.map((item: string) => (
                            <Option key={item} value={item}>
                              {item}
                            </Option>
                          ))}
                        </Select>
                      }
                    />
                  </Form.Item>
                  <span className="text-[12px] text-[var(--color-text-3)]">
                    {t('monitor.intergrations.timeoutDes')}
                  </span>
                </Form.Item>
              )}
              {['RabbitMQ', 'ActiveMQ', 'Tomcat'].includes(pluginName) && (
                <>
                  <Form.Item
                    label={t('monitor.intergrations.username')}
                    required
                  >
                    <Form.Item
                      noStyle
                      name="username"
                      rules={[
                        {
                          required: true,
                          message: t('common.required'),
                        },
                      ]}
                    >
                      <Input
                        className="w-[300px] mr-[10px]"
                        disabled={isEdit}
                      />
                    </Form.Item>
                    <span className="text-[12px] text-[var(--color-text-3)]">
                      {t('monitor.intergrations.usernameDes')}
                    </span>
                  </Form.Item>
                  <Form.Item
                    label={t('monitor.intergrations.password')}
                    required
                  >
                    <Form.Item
                      noStyle
                      name="password"
                      rules={[
                        {
                          required: true,
                          message: t('common.required'),
                        },
                      ]}
                    >
                      <Password
                        className="w-[300px] mr-[10px]"
                        disabled={isEdit}
                      />
                    </Form.Item>
                    <span className="text-[12px] text-[var(--color-text-3)]">
                      {t('monitor.intergrations.passwordDes')}
                    </span>
                  </Form.Item>
                </>
              )}
            </>
          ),
          configText: getConfigByPluginName(pluginName, 'manualCfgText'),
        };
      case 'docker':
        return {
          formItems: (
            <>
              <Form.Item required label={t('monitor.intergrations.endpoint')}>
                <Form.Item
                  noStyle
                  name="endpoint"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.endpointDes')}
                </span>
              </Form.Item>
            </>
          ),
          configText: `[[inputs.$config_type]]
    endpoint = "$endpoint"
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
        };
      case 'database':
        const isUsernameAndPasswordRequired = !['Redis', 'MongoDB'].includes(
          pluginName
        );
        return {
          formItems: (
            <>
              {pluginName === 'ElasticSearch' && (
                <Form.Item required label={t('monitor.intergrations.servers')}>
                  <Form.Item
                    noStyle
                    name="server"
                    rules={[
                      {
                        required: true,
                        message: t('common.required'),
                      },
                    ]}
                  >
                    <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                  </Form.Item>
                  <span className="text-[12px] text-[var(--color-text-3)]">
                    {t('monitor.intergrations.serversDes')}
                  </span>
                </Form.Item>
              )}
              <>
                <Form.Item
                  label={t('monitor.intergrations.username')}
                  required={isUsernameAndPasswordRequired}
                >
                  <Form.Item
                    noStyle
                    name="username"
                    rules={[
                      {
                        required: isUsernameAndPasswordRequired,
                        message: t('common.required'),
                      },
                    ]}
                  >
                    <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                  </Form.Item>
                  <span className="text-[12px] text-[var(--color-text-3)]">
                    {t('monitor.intergrations.usernameDes')}
                  </span>
                </Form.Item>
                <Form.Item
                  label={t('monitor.intergrations.password')}
                  required={isUsernameAndPasswordRequired}
                >
                  <Form.Item
                    noStyle
                    name="password"
                    rules={[
                      {
                        required: isUsernameAndPasswordRequired,
                        message: t('common.required'),
                      },
                    ]}
                  >
                    <Password
                      className="w-[300px] mr-[10px]"
                      disabled={isEdit}
                    />
                  </Form.Item>
                  <span className="text-[12px] text-[var(--color-text-3)]">
                    {t('monitor.intergrations.passwordDes')}
                  </span>
                </Form.Item>
              </>
              {pluginName !== 'ElasticSearch' && (
                <>
                  <Form.Item required label={t('monitor.intergrations.host')}>
                    <Form.Item
                      noStyle
                      name="host"
                      rules={[
                        {
                          required: true,
                          message: t('common.required'),
                        },
                      ]}
                    >
                      <Input
                        className="w-[300px] mr-[10px]"
                        disabled={isEdit}
                      />
                    </Form.Item>
                    <span className="text-[12px] text-[var(--color-text-3)]">
                      {t('monitor.intergrations.commonHostDes')}
                    </span>
                  </Form.Item>
                  <Form.Item required label={t('monitor.intergrations.port')}>
                    <Form.Item
                      noStyle
                      name="port"
                      rules={[
                        {
                          required: true,
                          message: t('common.required'),
                        },
                      ]}
                    >
                      <InputNumber
                        className="mr-[10px] w-[303px]"
                        min={1}
                        precision={0}
                        disabled={isEdit}
                      />
                    </Form.Item>
                    <span className="text-[12px] text-[var(--color-text-3)]">
                      {t('monitor.intergrations.commonPortDes')}
                    </span>
                  </Form.Item>
                </>
              )}
            </>
          ),
          configText: getConfigByPluginName(pluginName, 'manualCfgText'),
        };
      case 'http':
        return {
          formItems: (
            <>
              <Form.Item label={t('monitor.intergrations.username')} required>
                <Form.Item
                  noStyle
                  name="username"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.usernameDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.password')} required>
                <Form.Item
                  noStyle
                  name="password"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Password className="w-[300px] mr-[10px]" disabled={isEdit} />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.passwordDes')}
                </span>
              </Form.Item>
              {pluginName === 'VMWare' ? (
                <Form.Item required label={t('monitor.intergrations.host')}>
                  <Form.Item
                    noStyle
                    name="host"
                    rules={[
                      {
                        required: true,
                        message: t('common.required'),
                      },
                    ]}
                  >
                    <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                  </Form.Item>
                  <span className="text-[12px] text-[var(--color-text-3)]">
                    {t('monitor.intergrations.commonHostDes')}
                  </span>
                </Form.Item>
              ) : (
                !isEdit && (
                  <Form.Item required label="URL">
                    <Form.Item
                      noStyle
                      name="monitor_url"
                      rules={[
                        {
                          required: true,
                          message: t('common.required'),
                        },
                      ]}
                    >
                      <Input
                        className="w-[300px] mr-[10px]"
                        disabled={isEdit}
                      />
                    </Form.Item>
                    <span className="text-[12px] text-[var(--color-text-3)]">
                      {t('monitor.intergrations.urlDes')}
                    </span>
                  </Form.Item>
                )
              )}
            </>
          ),
          configText: getConfigByPluginName(pluginName, 'manualCfgText'),
        };
      case 'jmx':
        return {
          formItems: (
            <>
              <Form.Item label={t('monitor.intergrations.username')}>
                <Form.Item noStyle name="username">
                  <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.usernameDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.password')}>
                <Form.Item noStyle name="password">
                  <Password className="w-[300px] mr-[10px]" disabled={isEdit} />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.passwordDes')}
                </span>
              </Form.Item>
              <Form.Item required label="JmxUrl">
                <Form.Item
                  noStyle
                  name="monitor_url"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.urlDes')}
                </span>
              </Form.Item>
              {/* {isEdit && (
                <Form.Item required label="URL">
                  <Form.Item
                    noStyle
                    name="urls"
                    rules={[
                      {
                        required: true,
                        message: t('common.required'),
                      },
                    ]}
                  >
                    <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                  </Form.Item>
                  <span className="text-[12px] text-[var(--color-text-3)]">
                    {t('monitor.intergrations.childUrlDes')}
                  </span>
                </Form.Item>
              )} */}
              <Form.Item label={t('monitor.intergrations.listeningPort')}>
                <Form.Item noStyle name="LISTEN_PORT">
                  <InputNumber
                    className="w-[300px] mr-[10px]"
                    min={1}
                    precision={0}
                  />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.listeningPortDes')}
                </span>
              </Form.Item>
            </>
          ),
          configText: getConfigByPluginName(pluginName, 'manualCfgText'),
        };
      case 'exporter':
        return {
          formItems: (
            <>
              {/* {isEdit && (
                <Form.Item required label="URL">
                  <Form.Item
                    noStyle
                    name="urls"
                    rules={[
                      {
                        required: true,
                        message: t('common.required'),
                      },
                    ]}
                  >
                    <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                  </Form.Item>
                  <span className="text-[12px] text-[var(--color-text-3)]">
                    {t('monitor.intergrations.childUrlDes')}
                  </span>
                </Form.Item>
              )} */}
              <Form.Item label={t('monitor.intergrations.username')} required>
                <Form.Item
                  noStyle
                  name="USER"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.usernameDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.password')} required>
                <Form.Item
                  noStyle
                  name="PASSWORD"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Password className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.passwordDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.seviceName')} required>
                <Form.Item
                  noStyle
                  name="SERVICE_NAME"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.seviceNameDes')}
                </span>
              </Form.Item>
              <Form.Item
                label={t('monitor.intergrations.listeningPort')}
                required
              >
                <Form.Item
                  noStyle
                  name="LISTEN_PORT"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <InputNumber
                    className="w-[300px] mr-[10px]"
                    min={1}
                    precision={0}
                  />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.listeningPortDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.host')} required>
                <Form.Item
                  noStyle
                  name="HOST"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.commonHostDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.port')} required>
                <Form.Item
                  noStyle
                  name="PORT"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <InputNumber
                    className="w-[300px] mr-[10px]"
                    min={1}
                    precision={0}
                  />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.commonPortDes')}
                </span>
              </Form.Item>
            </>
          ),
          configText: getConfigByPluginName(pluginName, 'manualCfgText'),
        };
      case 'bkpull':
        return {
          formItems: (
            <>
              {/* {isEdit && (
                <Form.Item required label="URL">
                  <Form.Item
                    noStyle
                    name="urls"
                    rules={[
                      {
                        required: true,
                        message: t('common.required'),
                      },
                    ]}
                  >
                    <Input className="w-[300px] mr-[10px]" disabled={isEdit} />
                  </Form.Item>
                  <span className="text-[12px] text-[var(--color-text-3)]">
                    {t('monitor.intergrations.childUrlDes')}
                  </span>
                </Form.Item>
              )} */}
              <Form.Item label={t('monitor.intergrations.host')} required>
                <Form.Item
                  noStyle
                  name="host"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <Input className="w-[300px] mr-[10px]" />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.commonHostDes')}
                </span>
              </Form.Item>
              <Form.Item label={t('monitor.intergrations.port')} required>
                <Form.Item
                  noStyle
                  name="port"
                  rules={[
                    {
                      required: true,
                      message: t('common.required'),
                    },
                  ]}
                >
                  <InputNumber
                    className="w-[300px] mr-[10px]"
                    min={1}
                    precision={0}
                  />
                </Form.Item>
                <span className="text-[12px] text-[var(--color-text-3)]">
                  {t('monitor.intergrations.commonPortDes')}
                </span>
              </Form.Item>
            </>
          ),
          configText: getConfigByPluginName(pluginName, 'manualCfgText'),
        };
      default:
        return {
          formItems: (
            <Form.Item required label="URL">
              <Form.Item
                noStyle
                name="monitor_url"
                rules={[
                  {
                    required: true,
                    message: t('common.required'),
                  },
                ]}
              >
                <Input className="w-[300px] mr-[10px]" />
              </Form.Item>
              <span className="text-[12px] text-[var(--color-text-3)]">
                {t('monitor.intergrations.urlDes')}
              </span>
            </Form.Item>
          ),
          configText: `[[inputs.$config_type]]
    urls = ["$monitor_url"]
    interval = "$intervals"
    tags = { "instance_id"="$instance_id", "instance_type"="$instance_type", "collect_type"="$collect_type" }`,
        };
    }
  }, [collectType, t]);

  return result;
};

const useAssetMenuItems = (): MenuProps['items'] => {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        label: (
          <PermissionWrapper
            className="customMenuItem"
            requiredPermissions={['Edit']}
          >
            {t('common.batchEdit')}
          </PermissionWrapper>
        ),
        key: 'batchEdit',
      },
    ],
    [t]
  );
};
export { useColumnsAndFormItems, useFormItems, useAssetMenuItems };
