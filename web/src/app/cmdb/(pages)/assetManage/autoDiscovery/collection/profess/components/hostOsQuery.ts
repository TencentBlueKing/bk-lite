/** 自定义脚本按插件操作系统过滤主机。CMDB host.os_type：1 Linux，2 Windows。 */
export function customScriptHostOsQuery(osType?: string) {
  if (osType === 'windows') {
    return { field: 'os_type', type: 'list_any[]', value: ['2'] };
  }
  if (osType === 'linux') {
    return { field: 'os_type', type: 'list_any[]', value: ['1'] };
  }
  return null;
}
