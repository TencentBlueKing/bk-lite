# Cisco Meraki Wireless AP Guide

This plugin uses Telegraf `inputs.prometheus` to scrape Stargazer metrics collected from Meraki Dashboard API v1. It covers wireless AP packet loss and ethernet statuses. Organization, ethernet status, or packet-loss failures export `meraki_wireless_connect_status=0`. `ap_count` is the unique serial union of ethernet statuses and packet-loss data. Ethernet `link_up` prefers explicit `status` / `linkStatus` / `connected` fields, then falls back to `linkNegotiation.speed > 0` or duplex `full`/`half`.

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

- `GET /organizations/{id}/wireless/devices/ethernet/statuses`
- `GET /organizations/{id}/wireless/devices/packetLoss/byDevice`

Pagination follows the `Link: rel=next` response header.

## Verification

After one collection interval, confirm the instance appears and the connect-status metric continues to report.
