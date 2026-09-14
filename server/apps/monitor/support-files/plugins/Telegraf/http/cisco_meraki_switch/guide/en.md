# Cisco Meraki Switch Guide

This plugin uses Telegraf `inputs.prometheus` to scrape Stargazer metrics collected from Meraki Dashboard API v1. It covers switch port overview, ports by switch, and power history. Port overview and ports-by-switch are required; failures export `meraki_switch_connect_status=0`. Power history may soft-fail. Ports without `portId` are skipped. Port enabled/PoE values use enabled/disabled, not healthy/unhealthy.

## Prerequisites

- An organization API key used only for monitoring. The collector sends it as `X-Cisco-Meraki-API-Key`.
- The selected node can reach the regional Dashboard API host: `api.meraki.com / api.meraki.in / api.meraki.ca / api.meraki.cn / api.gov-meraki.com`.
- You know the organization ID, and the key can read that organization.
- Use an interval of at least 120 seconds when practical. The collector backs off on HTTP 429 using `Retry-After`. The organization budget is 10 requests per second.

## Setup

1. Select the regional endpoint. Use the host that matches the Dashboard organization region.
2. Enter the organization ID and organization API key. Do not put the key in the URL.
3. Select a container collector node that can reach Stargazer and Dashboard API.
4. Save and wait for at least one collection interval.

## APIs used by this plugin

- `GET /organizations/{id}/switch/ports/overview`
- `GET /organizations/{id}/switch/ports/bySwitch`
- `GET /organizations/{id}/summary/switch/power/history`

Pagination follows the `Link: rel=next` response header.

## Verification

After one collection interval, confirm the instance appears and the connect-status metric continues to report.
