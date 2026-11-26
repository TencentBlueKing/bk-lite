# K8s 事件接入走云区域入口

Status: implemented

## Problem Statement

K8s 集成指南把「BK-Lite 服务地址」默认成操作员浏览器打开的控制台地址，并写进 Event Exporter 的上报 URL。集群和这台控制台经常不在同一张网，事件到不了告警中心。页面还用内部产品名称呼这个地址。

集群名称和监控源仍然是两个字段。集群名称进入事件位置和标签。监控源进入 `push_source_id`，供规则、筛选和统计使用。两者不要收成一个框。

## Solution

操作员选择集群所在云区域，并继续填写集群名称和监控源。服务端读取该云区域的 `NODE_SERVER_URL`，保留协议、主机和端口，路径使用该 K8s 告警源配置的接收路径。页面只读展示解析结果，不能手填，也不能把浏览器地址交给服务端。

自定义云区域的 `NODE_SERVER_URL` 在区域创建时已经把主机换成区域代理。集群把事件交给代理。代理上的 Traefik 以 `PathPrefix(/)` 转到平台中心，告警仍进入现在这一套告警中心。默认云区域的地址就是中心，选它表示集群能直接访问中心。

## User Stories

1. As an integration operator, I want to choose the cloud region where the Kubernetes cluster can reach the platform proxy, so that the generated deployment reports events through that region instead of the console hostname.
2. As an integration operator, I want the resolved report address shown read-only, so that I can check firewall reachability without typing or overriding it.
3. As an integration operator, I want cluster name and monitoring source to stay separate, so that several clusters can share one monitoring source while each event still carries its own cluster name.
4. As an integration operator, I want download to fail when the selected region has no legal `NODE_SERVER_URL`, so that I do not apply a deployment that points nowhere.
5. As an integration operator, I want an already running exporter to keep its previous address until I download and apply again, so that this change does not rewrite live clusters.

## Implementation Decisions

- The public seams are the K8s deployment material endpoints and the K8s guide on the integration detail page. Zabbix and REST guides stay unchanged.
- Deployment requests send `cloud_region_id`, cluster name, monitoring source, team id, and the existing TLS skip flag. A client-supplied server URL is ignored.
- The same regional origin is used for the receiver URL and for the install command that curls the render API, because both calls originate from the cluster network.
- Region catalog comes from the existing cloud region list. Cloud regions are not owned by an organization, so the list is not filtered by team. The endpoint still requires integration detail permission.
- A missing or illegal `NODE_SERVER_URL` rejects material generation with a client error. The message names `NODE_SERVER_URL`.
- YAML environment variable names stay `BK_LITE_*`. `CLUSTER_NAME` receives the cluster name. `BK_LITE_PUSH_SOURCE_ID` receives the monitoring source and still defaults to `k8s`. `BK_LITE_SOURCE_ID` stays `k8s`.
- The guide removes the BK-Lite service address field. TLS copy no longer says BK-Lite. The monitoring source field remains.
- No new Traefik route. The proxy catch-all already forwards `/api/v1/alerts/`.

## Testing Decisions

- Test the deployment material HTTP boundary: the rendered YAML and install command use the selected region's `NODE_SERVER_URL`, ignore a hostile client URL, keep cluster name and monitoring source distinct, and reject a missing or illegal region address.
- Test the guide as a user sees it: choosing a region shows the server-returned address, download sends the region id rather than a typed URL, and download stays disabled until that address exists.
- Prior art is the existing K8s install view tests and the alarm guide component tests. Node management is stubbed at the alerts view boundary.

## Out of Scope

- A separate alarm center per cloud region.
- Renaming `BK_LITE_*` keys.
- Merging cluster name and monitoring source.
- Changing Zabbix or REST webhook hosts.
- Rewriting exporters that are already applied.

## Further Notes

- 已确认：2026-11-26。监控源输入框保留，默认仍是 `k8s`。
- 区域代理证书仍由现有「跳过 TLS 证书校验」处理。
- 验证：`server` 下 `apps/alerts/tests/test_alert_source_views.py` 的区域地址、缺失地址、非法地址和目录接口用例通过；同目录安装与渲染用例此前 101 passed。`web` 下 `src/app/alarm/components/__tests__/k8s-guide-cloud-region.test.tsx` 3 passed。未打开真实集成详情页。
