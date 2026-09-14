# Cisco Meraki Organization Guide

This plugin uses Telegraf `inputs.prometheus` to scrape Stargazer metrics collected from Meraki Dashboard API v1. It covers the configured organization, its network list, and organization health. Collection, auth, or API failures still export `meraki_org_connect_status=0` so the unavailable-API policy can fire.

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

- `GET /organizations/{id}`
- `GET /organizations/{id}/networks`

Pagination follows the `Link: rel=next` response header.

## Verification

After one collection interval, confirm the instance appears and the connect-status metric continues to report.
