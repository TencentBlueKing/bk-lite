import React from 'react';
import { Form, Input, Radio, Select } from 'antd';
import GroupTreeSelector from '@/components/group-tree-select';
import IntegrationSettingRow from '@/components/integration-setting-row';

interface SelectOption {
  value: string | number;
  label: React.ReactNode;
}

export interface K8sAccessAssetFieldsCopy {
  accessAsset: React.ReactNode;
  accessAssetDesc: React.ReactNode;
  newAsset: React.ReactNode;
  existingAsset: React.ReactNode;
  clusterName: React.ReactNode;
  clusterNamePlaceholder: string;
  clusterNameDesc: React.ReactNode;
  organization: React.ReactNode;
  organizationDesc: React.ReactNode;
  k8sCluster: React.ReactNode;
  k8sClusterDesc: React.ReactNode;
  selectClusterPlaceholder: string;
  cloudRegion: React.ReactNode;
  cloudRegionDesc: React.ReactNode;
  selectCloudRegionPlaceholder: string;
  requiredMessage: string;
  selectTip: string;
}

export interface K8sAccessAssetFieldsProps {
  controlWidth?: number;
  copy: K8sAccessAssetFieldsCopy;
  cloudRegionLoading?: boolean;
  cloudRegionOptions: SelectOption[];
  existingClusterLoading?: boolean;
  existingClusterOptions: SelectOption[];
  existingClusterShowSearch?: boolean;
}

const K8sAccessAssetFields: React.FC<K8sAccessAssetFieldsProps> = ({
  controlWidth = 300,
  copy,
  cloudRegionLoading = false,
  cloudRegionOptions,
  existingClusterLoading = false,
  existingClusterOptions,
  existingClusterShowSearch = false,
}) => {
  return (
    <>
      <Form.Item label={copy.accessAsset} required>
        <IntegrationSettingRow
          control={
            <Form.Item
              name="accessType"
              noStyle
              rules={[{ required: true, message: copy.requiredMessage }]}
            >
              <Radio.Group style={{ width: controlWidth }}>
                <Radio value="new">{copy.newAsset}</Radio>
                <Radio value="existing">{copy.existingAsset}</Radio>
              </Radio.Group>
            </Form.Item>
          }
          description={copy.accessAssetDesc}
        />
      </Form.Item>

      <Form.Item
        noStyle
        shouldUpdate={(prevValues, currentValues) =>
          prevValues.accessType !== currentValues.accessType
        }
      >
        {({ getFieldValue }) =>
          getFieldValue('accessType') === 'new' ? (
            <>
              <Form.Item label={copy.clusterName} required>
                <IntegrationSettingRow
                  control={
                    <Form.Item
                      name="name"
                      noStyle
                      rules={[{ required: true, message: copy.requiredMessage }]}
                    >
                      <Input
                        placeholder={copy.clusterNamePlaceholder}
                        style={{ width: controlWidth }}
                      />
                    </Form.Item>
                  }
                  description={copy.clusterNameDesc}
                />
              </Form.Item>

              <Form.Item label={copy.organization} required>
                <IntegrationSettingRow
                  control={
                    <Form.Item
                      name="organizations"
                      noStyle
                      rules={[{ required: true, message: copy.requiredMessage }]}
                    >
                      <GroupTreeSelector
                        style={{ width: controlWidth }}
                        placeholder={copy.selectTip}
                      />
                    </Form.Item>
                  }
                  description={copy.organizationDesc}
                />
              </Form.Item>
            </>
          ) : (
            <Form.Item label={copy.k8sCluster} required>
              <IntegrationSettingRow
                control={
                  <Form.Item
                    name="k8sCluster"
                    noStyle
                    rules={[{ required: true, message: copy.requiredMessage }]}
                  >
                    <Select
                      showSearch={existingClusterShowSearch}
                      loading={existingClusterLoading}
                      placeholder={copy.selectClusterPlaceholder}
                      style={{ width: controlWidth }}
                      options={existingClusterOptions}
                    />
                  </Form.Item>
                }
                description={copy.k8sClusterDesc}
              />
            </Form.Item>
          )
        }
      </Form.Item>

      <Form.Item label={copy.cloudRegion} required>
        <IntegrationSettingRow
          control={
            <Form.Item
              name="cloud_region_id"
              noStyle
              rules={[{ required: true, message: copy.requiredMessage }]}
            >
              <Select
                loading={cloudRegionLoading}
                placeholder={copy.selectCloudRegionPlaceholder}
                style={{ width: controlWidth }}
                options={cloudRegionOptions}
              />
            </Form.Item>
          }
          description={copy.cloudRegionDesc}
        />
      </Form.Item>
    </>
  );
};

export default K8sAccessAssetFields;
export {
  createLogK8sAccessAssetFieldsCopy,
  createMonitorK8sAccessAssetFieldsCopy,
} from './presets';
