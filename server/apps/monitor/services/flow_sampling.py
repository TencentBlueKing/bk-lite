class FlowSamplingService:
    CANDIDATE_FIELDS = (
        "SAMPLING_INTERVAL",
        "SAMPLING_ALGORITHM",
        "sampling_rate",
        "samplingRate",
    )

    @classmethod
    def normalize_payload(cls, payload: dict, *, fallback_sampling_rate):
        normalized = dict(payload)

        if normalized.get("effective_sampling_rate") not in (None, ""):
            normalized["sampling_rate_source"] = "reported_effective_sampling_rate"
            return normalized

        for field in cls.CANDIDATE_FIELDS:
            if normalized.get(field) not in (None, ""):
                normalized["effective_sampling_rate"] = normalized[field]
                normalized["sampling_rate_source"] = f"normalized_from_{field}"
                return normalized

        normalized["effective_sampling_rate"] = fallback_sampling_rate
        normalized["sampling_rate_source"] = "fallback_sampling_rate"
        return normalized
