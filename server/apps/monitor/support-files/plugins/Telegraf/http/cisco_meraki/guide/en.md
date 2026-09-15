# Cisco Meraki Guide

Cisco Meraki is a single Network Device capability. Create one instance under **Network Device → Cisco Meraki** with a shared organization API key and regional endpoint. That one access collects organization, network, device, wireless AP, switch, and MX (appliance) metrics for the organization. Telegraf `inputs.prometheus` scrapes Dashboard API v1 data from `/cisco_meraki/metrics`. Metric names use the `meraki_*` prefix.

If the organization-level request fails, every face exports `connect_status=0`. If only the device, wireless AP, switch, or MX family fails, only that family's connect-status gauge is set to `0`.

## What it monitors

One access covers these faces:

- **Organization**: Dashboard connectivity and network count
- **Network**: networks in the organization
- **Device**: inventory, availability, uplink latency and loss
- **Wireless AP**: AP count, upstream/downstream loss, Ethernet link
- **Switch**: active/inactive ports and PoE power draw
- **MX (appliance)**: VPN network count, peer reachability, latency, and utilization

## Prerequisites

- A Meraki Dashboard **organization API key** used for monitoring (read-only is enough). The collector sends it as `X-Cisco-Meraki-API-Key`. Do not put the key in the URL.
- The key can read the target organization. Find the organization ID in Dashboard organization settings.
- The selected container collector node can reach the regional Dashboard API host: `api.meraki.com` / `api.meraki.in` / `api.meraki.ca` / `api.meraki.cn` / `api.gov-meraki.com`. Use the host that matches the organization region.
- Use an interval of at least 120 seconds when practical. One scrape issues multiple Dashboard requests. Shorter intervals are more likely to hit the 10 requests/second/organization budget. The collector backs off on HTTP 429 using `Retry-After`.

## Integration steps

1. Open monitor integration, go to **Network Device → Cisco Meraki**, and create an instance.
2. Select the **regional endpoint** that matches the Dashboard organization region.
3. Enter the **organization ID**, the shared **organization API key**, and an instance name. Select a container collector node that can reach Dashboard API.
4. Save and start collection. Wait at least one interval (default 120 seconds).

## Form fields

| Field | Required | Default | Description |
| --- | --- | --- | --- |
| Regional Endpoint | Yes | `https://api.meraki.com` | Dashboard API regional root. The collector requests `/api/v1`. |
| Organization ID | Yes | none | Meraki organization ID. |
| Organization API Key | Yes | none | Organization key, injected into the request header via an environment variable. |
| Interval | Yes | `120` s | Collection interval. Shorter values are more likely to hit API rate limits. |
| Node | Yes | none | Container collector node. |
| Instance Name | Yes | none | Display name in the platform. |
| Group | No | none | Optional instance group. |

## After connect

After one collection interval, on the Cisco Meraki object page confirm:

- `meraki_org_connect_status` is `1`, meaning the organization-level Dashboard API call succeeded.
- Main dashboard cards have data: connect status, network count, device count, wireless AP count, switch active port count, and MX VPN network count.
- Network / Device / Wireless AP / Switch / Appliance sub-views show the matching metric groups.

## Troubleshooting

### Auth or permission failure (HTTP 401 / 403)

Check that the organization API key is complete, belongs to this organization, and can read it. Do not put the key in the URL or ordinary headers.

### Organization not found or wrong region (HTTP 404)

Confirm the organization ID and that the regional endpoint matches the Dashboard region for that organization.

### Rate limited (HTTP 429)

Increase the interval (120 seconds or more is recommended). The collector backs off using `Retry-After`. Persistent 429s usually mean other high-rate API clients share the same organization budget.

### `connect_status` is 0 or dashboard cards are empty

Check `meraki_org_connect_status` first. If it is `0`, the organization-level request failed and none of the faces will be healthy. If the organization gauge is `1` but one family is `0`, check Dashboard permissions and reachability for that face (for example the organization has no switches or MX appliances).

## APIs used by this capability

The collector node must reach these Dashboard API v1 paths. Pagination follows the `Link: rel=next` response header.

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
