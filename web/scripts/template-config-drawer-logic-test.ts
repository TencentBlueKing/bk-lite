import * as assert from 'node:assert/strict';
import {
  getPluginConfigContentState,
  getPluginConfigFetchDecision,
  isSameTemplatePlugin
} from '../src/app/monitor/(pages)/integration/asset/templateConfigDrawerLogic';
import { DataMapper } from '../src/app/monitor/hooks/integration/useDataMapper';

const hostRemote = {
  name: 'Host Remote',
  plugin_id: 30,
  collector: 'Telegraf',
  collect_type: 'http',
  status: 'normal',
  collect_mode: 'auto',
  time: ''
};
const windowsWmi = {
  name: 'Windows WMI',
  plugin_id: 48,
  collector: 'Telegraf',
  collect_type: 'http',
  status: 'normal',
  collect_mode: 'auto',
  time: ''
};
const reportedOnly = {
  name: 'Windows WMI',
  plugin_id: 48,
  collector: 'Telegraf',
  collect_type: 'http',
  status: 'normal',
  collect_mode: 'manual',
  time: ''
};

assert.equal(isSameTemplatePlugin(hostRemote, hostRemote), true);
assert.equal(isSameTemplatePlugin(hostRemote, windowsWmi), false);
assert.deepEqual(getPluginConfigFetchDecision(hostRemote, windowsWmi), {
  shouldChangeSelection: true,
  shouldFetchConfig: true
});
assert.deepEqual(getPluginConfigFetchDecision(hostRemote, hostRemote), {
  shouldChangeSelection: false,
  shouldFetchConfig: false
});
assert.deepEqual(getPluginConfigFetchDecision(hostRemote, reportedOnly), {
  shouldChangeSelection: true,
  shouldFetchConfig: false
});
assert.equal(getPluginConfigContentState(reportedOnly, []), 'reportedOnly');
assert.equal(
  getPluginConfigContentState({ ...hostRemote, configured: true }, []),
  'missingConfig'
);
assert.equal(
  getPluginConfigContentState({ ...hostRemote, configured: true }, [{ id: 1 }]),
  'configured'
);

const oracleConfig = {
  child: {
    id: 'oracle-child-cfg',
    env_config: {
      'HOST__ORACLE-CHILD-CFG': '10.10.41.149',
      'PORT__ORACLE-CHILD-CFG': 1521
    },
    content: {
      config: {
        interval: '10s'
      }
    }
  }
};
const oracleHostTransform = {
  origin_path: 'child.env_config.HOST__{{config_id}}'
};
const oracleIntervalTransform = {
  origin_path: 'child.content.config.interval',
  to_form: {
    regex: '^(\\d+)s$'
  },
  to_api: {
    suffix: 's'
  }
};
assert.equal(
  DataMapper.transformValue(null, oracleHostTransform, 'toForm', oracleConfig),
  '10.10.41.149'
);
assert.equal(
  DataMapper.transformValue(null, oracleIntervalTransform, 'toForm', oracleConfig),
  '10'
);
const resolvedOracleHostPath = DataMapper.resolvePathVariables(
  oracleHostTransform.origin_path,
  oracleConfig
);
const updatedOracleConfig = structuredClone(oracleConfig);
DataMapper.setNestedValue(updatedOracleConfig, resolvedOracleHostPath, '10.10.41.150');
assert.equal(
  updatedOracleConfig.child.env_config['HOST__ORACLE-CHILD-CFG'],
  '10.10.41.150'
);
assert.equal(
  DataMapper.transformValue('30', oracleIntervalTransform, 'toApi'),
  '30s'
);

console.log('template config drawer logic tests passed');
