export type ExecStatusKey = 'add' | 'update' | 'delete';

export interface ExecStatus {
  color: string;
  text: string;
}

type ExecStatusMapType = {
  [K in ExecStatusKey]: ExecStatus;
};

export const createExecStatusMap = (
  t: (key: string) => string
): ExecStatusMapType => ({
  add: {
    color: 'success',
    text: t('Collection.syncStatus.add'),
  },
  update: {
    color: 'processing',
    text: t('Collection.syncStatus.update'),
  },
  delete: {
    color: 'error',
    text: t('Collection.syncStatus.delete'),
  },
});

export const EXEC_STATUS = {
  UNEXECUTED: 0,
  COLLECTING: 1,
  SUCCESS: 2,
  ERROR: 3,
  TIMEOUT: 4,
  WRITING: 5,
  FORCE_STOP: 6,
  PENDING_APPROVAL: 7,
} as const;

export type ExecStatusType = (typeof EXEC_STATUS)[keyof typeof EXEC_STATUS];

export const getExecStatusConfig = (t: (key: string) => string) => ({
  [EXEC_STATUS.UNEXECUTED]: {
    text: t('Collection.syncStatus.unexecuted'),
    color: 'var(--color-text-3)',
  },
  [EXEC_STATUS.COLLECTING]: {
    text: t('Collection.syncStatus.collecting'),
    color: 'var(--color-primary)',
  },
  [EXEC_STATUS.SUCCESS]: {
    text: t('Collection.syncStatus.success'),
    color: '#4ACF88',
  },
  [EXEC_STATUS.ERROR]: {
    text: t('Collection.syncStatus.error'),
    color: '#FF6A57',
  },
  [EXEC_STATUS.TIMEOUT]: {
    text: t('Collection.syncStatus.timeout'),
    color: '#FF6A57',
  },
  [EXEC_STATUS.WRITING]: {
    text: t('Collection.syncStatus.writing'),
    color: 'var(--color-primary)',
  },
  [EXEC_STATUS.FORCE_STOP]: {
    text: t('Collection.syncStatus.forceStop'),
    color: '#FF6A57',
  },
  [EXEC_STATUS.PENDING_APPROVAL]: {
    text: t('Collection.syncStatus.pendingApproval'),
    color: '#F7BA1E',
  },
});

export const CYCLE_OPTIONS = {
  DAILY: 'timing',
  INTERVAL: 'cycle',
  ONCE: 'close',
} as const;

export const ENTER_TYPE = {
  AUTOMATIC: 'automatic',
  APPROVAL: 'approval',
} as const;

// 密码占位符，用于编辑时隐藏真实密码
export const PASSWORD_PLACEHOLDER = '******';

export const K8S_FORM_INITIAL_VALUES = {
  instId: undefined,
  cycle: CYCLE_OPTIONS.ONCE,
  intervalMinutes: 60,
  timeout: 60,
};

export const VM_FORM_INITIAL_VALUES = {
  instId: undefined,
  cycle: CYCLE_OPTIONS.ONCE,
  enterType: ENTER_TYPE.AUTOMATIC,
  port: '443',
  timeout: 600,
  sslVerify: false,
};

export const SNMP_FORM_INITIAL_VALUES = {
  instId: undefined,
  cycle: CYCLE_OPTIONS.ONCE,
  enterType: ENTER_TYPE.AUTOMATIC,
  version: 'v2',
  snmp_port: '161',
  timeout: 60,
  level: 'authNoPriv',
  integrity: 'sha',
  privacy: 'aes',
};

export const SQL_FORM_INITIAL_VALUES = {
  instId: undefined,
  cycle: CYCLE_OPTIONS.ONCE,
  enterType: ENTER_TYPE.AUTOMATIC,
  name: '',
  password: '',
  port: '3306',
  timeout: 60,
};

export const CLOUD_FORM_INITIAL_VALUES = {
  instId: undefined,
  cycle: CYCLE_OPTIONS.ONCE,
  enterType: ENTER_TYPE.APPROVAL,
  accessKey: '',
  accessSecret: '',
  regionId: '',
  timeout: 600
};

export const HOST_FORM_INITIAL_VALUES = {
  instId: undefined,
  cycle: CYCLE_OPTIONS.ONCE,
  enterType: ENTER_TYPE.AUTOMATIC,
  username: '',
  password: '',
  port: '22',
  timeout: 60
};

export const validateCycleTime = (
  type: string,
  value: any,
  message: string
) => {
  if (!value && (type === 'daily' || type === 'every')) {
    return Promise.reject(new Error(message));
  }
  return Promise.resolve();
};

export type AlertType = 'info' | 'warning' | 'error';

export interface TabConfig {
  count: number;
  label: string;
  alertType: AlertType;
  columns: {
    title: string;
    dataIndex: string;
    width?: number;
  }[];
}
interface ValidationContext {
  form: any;
  t: (key: string) => string;
  taskType?: string;
}

const baseValidators = {
  required: (message: string) => ({ required: true, message }),
};

const cycleValidators = (context: ValidationContext) => ({
  dailyTime: [
    {
      validator: (_: any, value: any) => {
        const cycle = context.form.getFieldValue('cycle');
        if (cycle === CYCLE_OPTIONS.DAILY && !value) {
          return Promise.reject(new Error(context.t('Collection.selectTime')));
        }
        return Promise.resolve();
      },
    },
  ],
  intervalValue: [
    {
      validator: (_: any, value: any) => {
        const cycle = context.form.getFieldValue('cycle');
        if (cycle === CYCLE_OPTIONS.INTERVAL && !value) {
          return Promise.reject(
            new Error(context.t('Collection.k8sTask.intervalRequired'))
          );
        }
        return Promise.resolve();
      },
    },
  ],
});

export const createTaskValidationRules = (context: ValidationContext) => {
  const { t, form, taskType } = context;

  const baseRules = {
    taskName: [
      baseValidators.required(
        `${t('common.inputMsg')}${t('Collection.taskNameLabel')}`
      ),
    ],
    cycle: [
      baseValidators.required(
        `${t('common.selectMsg')}${t('Collection.cycle')}`
      ),
    ],
    instId: [baseValidators.required(`${t('required')}`)],
    timeout: [
      baseValidators.required(
        `${t('common.inputMsg')}${t('Collection.timeout')}`
      ),
    ],
    ...cycleValidators(context),
    assetInst: [
      {
        validator: () => {
          const selectedData = form.getFieldValue('assetInst');
          if (!selectedData?.length) {
            return Promise.reject(new Error(t('required')));
          }
          return Promise.resolve();
        }
      }
    ],
  };

  if (taskType === 'vm') {
    return {
      ...baseRules,
      enterType: [
        baseValidators.required(
          `${t('common.selectMsg')}${t('Collection.enterType')}`
        ),
      ],
      accessPointId: [
        baseValidators.required(
          `${t('common.selectMsg')}${t('Collection.accessPoint')}`
        ),
      ],
      username: [
        baseValidators.required(
          `${t('common.inputMsg')}${t('Collection.VMTask.username')}`
        ),
      ],
      password: [
        baseValidators.required(
          `${t('common.inputMsg')}${t('Collection.VMTask.password')}`
        ),
      ],
      port: [
        baseValidators.required(
          `${t('common.inputMsg')}${t('Collection.port')}`
        ),
      ],
      sslVerify: [
        baseValidators.required(
          `${t('common.selectMsg')}${t('Collection.VMTask.sslVerify')}`
        ),
      ],
    };
  }

  if (taskType === 'snmp') {
    return {
      ...baseRules,
      enterType: [
        baseValidators.required(
          `${t('common.selectMsg')}${t('Collection.enterType')}`
        ),
      ],
      snmpVersion: [
        baseValidators.required(
          `${t('common.selectMsg')}${t('Collection.SNMPTask.version')}`
        ),
      ],
      port: [
        baseValidators.required(
          `${t('common.inputMsg')}${t('Collection.port')}`
        ),
      ],
      communityString: [
        {
          validator: (_: any, value: any) => {
            const version = context.form.getFieldValue('version');
            if (['v2', 'v2C'].includes(version) && !value) {
              return Promise.reject(
                new Error(
                  `${t('common.inputMsg')}${t('Collection.SNMPTask.communityString')}`
                )
              );
            }
            return Promise.resolve();
          },
        },
      ],
      userName: [
        {
          validator: (_: any, value: any) => {
            const version = context.form.getFieldValue('version');
            if (version === 'v3' && !value) {
              return Promise.reject(
                new Error(
                  `${t('common.inputMsg')}${t('Collection.SNMPTask.userName')}`
                )
              );
            }
            return Promise.resolve();
          },
        },
      ],
      authPassword: [
        {
          validator: (_: any, value: any) => {
            const version = context.form.getFieldValue('snmpVersion');
            if (version === 'v3' && !value) {
              return Promise.reject(
                new Error(
                  `${t('common.inputMsg')}${t('Collection.SNMPTask.authPassword')}`
                )
              );
            }
            return Promise.resolve();
          },
        },
      ],
      encryptKey: [
        {
          validator: (_: any, value: any) => {
            const version = context.form.getFieldValue('version');
            const securityLevel = context.form.getFieldValue('level');
            if (version === 'v3' && securityLevel === 'authPriv' && !value) {
              return Promise.reject(
                new Error(
                  `${t('common.inputMsg')}${t('Collection.SNMPTask.encryptKey')}`
                )
              );
            }
            return Promise.resolve();
          },
        },
      ],
    };
  }

  return baseRules;
};

export const CREATE_TASK_DETAIL_CONFIG = (t: (key: string) => string) => ({
  add: {
    count: 0,
    label: t('Collection.syncStatus.add'),
    alertType: 'warning',
    columns: [
      { title: '对象类型', dataIndex: 'model_id', width: 140 },
      { title: '实例名', dataIndex: 'inst_name', width: 250 },
    ],
  },
  update: {
    count: 4,
    label: t('Collection.syncStatus.update'),
    alertType: 'warning',
    columns: [
      { title: '对象类型', dataIndex: 'model_id', width: 140 },
      { title: '实例名', dataIndex: 'inst_name', width: 250 },
    ],
  },
  delete: {
    count: 3,
    label: t('Collection.syncStatus.delete'),
    alertType: 'warning',
    columns: [
      { title: '对象类型', dataIndex: 'model_id', width: 140 },
      { title: '实例名', dataIndex: 'inst_name', width: 250 },
    ],
  },
});

export const NETWORK_DEVICE_OPTIONS = [
  {
    key: 'switch',
    label: '交换机',
  },
  {
    key: 'router',
    label: '路由器',
  },
  {
    key: 'firewall',
    label: '防火墙',
  },
  {
    key: 'loadbalance',
    label: '负载均衡',
  },
]


