import React from 'react';
import { Form } from 'antd';
import type { FormInstance } from 'antd';
import IntegrationStepCallout, {
  type IntegrationStepCalloutProps,
} from '@/components/integration-step-callout';
import K8sAccessAssetFields, {
  type K8sAccessAssetFieldsProps,
} from '@/components/k8s-access-asset-fields';
import SectionHeader from '@/components/section-header';

interface IntegrationK8sAccessConfigShellProps {
  form: FormInstance;
  initialValues?: Record<string, unknown>;
  sectionTitle: React.ReactNode;
  sectionIconType?: string;
  stepCallout: IntegrationStepCalloutProps;
  assetFieldsProps: K8sAccessAssetFieldsProps;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  formClassName?: string;
  actionsClassName?: string;
}

const IntegrationK8sAccessConfigShell: React.FC<
  IntegrationK8sAccessConfigShellProps
> = ({
  form,
  initialValues,
  sectionTitle,
  sectionIconType = 'settings-fill',
  stepCallout,
  assetFieldsProps,
  children,
  actions,
  className = 'p-0',
  formClassName = 'w-full',
  actionsClassName = 'mt-6 flex justify-end',
}) => {
  return (
    <div className={className}>
      <IntegrationStepCallout {...stepCallout} />

      <Form
        form={form}
        layout="vertical"
        className={formClassName}
        initialValues={initialValues}
      >
        <SectionHeader title={sectionTitle} iconType={sectionIconType} />
        <K8sAccessAssetFields {...assetFieldsProps} />
        {children}
        {actions ? <div className={actionsClassName}>{actions}</div> : null}
      </Form>
    </div>
  );
};

export default IntegrationK8sAccessConfigShell;
