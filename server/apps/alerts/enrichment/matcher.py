from apps.alerts.utils.typed_rules import matches_payload


def event_matches(event, match_rules):
    return matches_payload(event, match_rules, "enrichment")
