import { OBJECT_DEFAULT_ICON } from '@/app/monitor/constants';
import { withDashboardReturnContext } from '@/app/monitor/dashboards/shared/utils';
import { encodeInstanceIdValuesParam } from '@/app/monitor/dashboards/shared/utils/instance';

type DashboardUrlResolver = (
  objectName?: string | null,
  objectDisplayName?: string | null,
  queryString?: string
) => string;

interface AssetViewMonitorItem {
  name?: string | null;
  display_name?: string | null;
  icon?: string | null;
  instance_id_keys?: unknown;
}

interface AssetViewRow {
  instance_id?: unknown;
  instance_name?: unknown;
  instance_id_values?: unknown;
}

interface BuildAssetViewUrlOptions {
  objectId?: unknown;
  monitorItem?: AssetViewMonitorItem | null;
  row: AssetViewRow;
  resolveProfessionalDashboardUrl?: DashboardUrlResolver;
}

const toParamValue = (value: unknown) => {
  if (Array.isArray(value)) return encodeInstanceIdValuesParam(value);
  if (value === null || value === undefined) return '';
  return String(value);
};

const resolveInstanceIdKeys = (instanceIdKeys: unknown) => {
  if (Array.isArray(instanceIdKeys) && instanceIdKeys.length) {
    return instanceIdKeys.join(',');
  }

  return 'instance_id';
};

export const buildAssetViewUrl = ({
  objectId,
  monitorItem,
  row,
  resolveProfessionalDashboardUrl
}: BuildAssetViewUrlOptions) => {
  const params = new URLSearchParams({
    monitorObjId: toParamValue(objectId),
    name: toParamValue(monitorItem?.name),
    monitorObjDisplayName: toParamValue(monitorItem?.display_name),
    instance_id: toParamValue(row.instance_id),
    icon: toParamValue(monitorItem?.icon || OBJECT_DEFAULT_ICON),
    instance_name: toParamValue(row.instance_name),
    instance_id_values: toParamValue(row.instance_id_values),
    instance_id_keys: resolveInstanceIdKeys(monitorItem?.instance_id_keys)
  });
  const dashboardParams = withDashboardReturnContext(params, {
    objectId: toParamValue(objectId),
    objectName: toParamValue(monitorItem?.display_name || monitorItem?.name),
    source: 'integration'
  });
  const queryString = dashboardParams.toString();
  const professionalDashboardUrl =
    resolveProfessionalDashboardUrl?.(
      monitorItem?.name,
      monitorItem?.display_name,
      queryString
    ) || '';

  return professionalDashboardUrl || `/monitor/view/detail?${queryString}`;
};
