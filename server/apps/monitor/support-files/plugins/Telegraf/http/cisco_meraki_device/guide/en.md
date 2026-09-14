# Cisco Meraki Device Guide

This plugin uses Telegraf `inputs.prometheus` to scrape Stargazer metrics collected from Meraki Dashboard API v1. It covers device inventory, availabilities, and uplink loss/latency. Organization, device inventory, or availability failures export `meraki_device_connect_status=0`. Uplink loss/latency is optional and may soft-fail without marking the collection healthy. Devices without an availability status are not reported as dormant.

## Prerequisites

- An organization API key used only for monitoring. The collector sends it as `X-Cisco-Meraki-API-Key`.
- The selected node can reach the regional Dashboard API host: `api.meraki.com / api.meraki.in / api.meraki.ca / api.meraki.cn / api.gov-meraki.com`.
- You know the organization ID, and the key can read that organization.
- Use an interval of at least 120 seconds when practical. The collector backs off on HTTP 429 using `Retry-After`. The organization budget is 10 requests per second.

## Setup

1. Select the regional endpoint. Use the host that matches the Dashboard organization region.
2. Enter the organization ID and organization API key. Do not put the key in the URL.
3. Optionally change the uplink timespan (1–300 seconds, default 300).
4. Select a container collector node that can reach Stargazer and Dashboard API.
5. Save and wait for at least one collection interval.

## APIs used by this plugin

- `GET /organizations/{id}/devices`
- `GET /organizations/{id}/devices/availabilities`
- `GET /organizations/{id}/devices/uplinksLossAndLatency`

Pagination follows the `Link: rel=next` response header.

## Verification

After one collection interval, confirm the instance appears and the connect-status metric continues to report.
