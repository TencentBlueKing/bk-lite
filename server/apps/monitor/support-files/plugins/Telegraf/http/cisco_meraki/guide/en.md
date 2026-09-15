# Cisco Meraki Guide

This plugin uses Telegraf `inputs.prometheus` to scrape Stargazer metrics collected from Meraki Dashboard API v1. One access form stores a single organization API key and regional endpoint. Stargazer then scrapes organization, device, wireless AP, switch, and MX (appliance) metric families sequentially from `/cisco_meraki/metrics`. Organization-level failure exports every family `connect_status=0`. Device, wireless, switch, or MX family failure only zeros that family's connect-status gauge.

## Existing instances must be reconfigured (breaking change)

The previous five independent plugins (Cisco Meraki Organization / Device / Wireless AP / Switch / Appliance) are retired. They are now one **Cisco Meraki** capability under Network Device. `plugin_init` removes the old plugins and inventory objects. **Existing instances from those five plugins are not migrated automatically.**

After upgrade:

1. Disable and delete the old five independent access instances if they still appear in the console.
2. Reconfigure under **Network Device → Cisco Meraki** with the same organization API key and regional endpoint.
3. Save, wait for at least one collection interval, then confirm all five metric families in the Network / Device / Wireless AP / Switch / Appliance sub-views.

Prometheus metric names remain `meraki_*`. The scrape path is now `/cisco_meraki/metrics`. Do not keep configuring the retired five plugins.

## Prerequisites

- An organization API key used only for monitoring. The collector sends it as `X-Cisco-Meraki-API-Key`.
- The selected node can reach the regional Dashboard API host: `api.meraki.com / api.meraki.in / api.meraki.ca / api.meraki.cn / api.gov-meraki.com`.
- You know the organization ID, and the key can read that organization.
- Use an interval of at least 120 seconds when practical. One scrape issues multiple Dashboard requests. The collector backs off on HTTP 429 using `Retry-After`. The organization budget is 10 requests per second.

## Setup

1. Select the regional endpoint. Use the host that matches the Dashboard organization region.
2. Enter the organization ID and organization API key. Do not put the key in the URL.
3. Select a container collector node that can reach Stargazer and Dashboard API.
4. Save and wait for at least one collection interval. After ingest, use the Cisco Meraki object tabs for Network / Device / Wireless AP / Switch / Appliance sub-views.

## APIs used by this plugin

- `GET /organizations/{id}`
- `GET /organizations/{id}/networks`
- `GET /organizations/{id}/devices`
- `GET /organizations/{id}/devices/availabilities`
- `GET /organizations/{id}/devices/uplinksLossAndLatency` (optional; soft-fail)
- `GET /organizations/{id}/wireless/devices/ethernet/statuses`
- `GET /organizations/{id}/wireless/devices/packetLoss/byDevice`
- `GET /organizations/{id}/switch/ports/overview`
- `GET /organizations/{id}/switch/ports/bySwitch`
- `GET /organizations/{id}/summary/switch/power/history` (optional)
- `GET /organizations/{id}/appliance/vpn/statuses`
- `GET /organizations/{id}/appliance/vpn/stats` (optional)
- `GET /organizations/{id}/summary/top/appliances/byUtilization` (optional)

Pagination follows the `Link: rel=next` response header.

## Verification

After one collection interval, confirm the instance appears and `meraki_org_connect_status` plus the per-family connect-status gauges continue to report.
