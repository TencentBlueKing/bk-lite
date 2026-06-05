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

        effective_sampling_rate = cls._parse_sampling_rate(normalized.get("effective_sampling_rate"))
        if effective_sampling_rate is not None:
            normalized["effective_sampling_rate"] = effective_sampling_rate
            normalized["sampling_rate_source"] = "reported_effective_sampling_rate"
            return normalized

        for field in cls.CANDIDATE_FIELDS:
            effective_sampling_rate = cls._parse_sampling_rate(normalized.get(field))
            if effective_sampling_rate is not None:
                normalized["effective_sampling_rate"] = effective_sampling_rate
                normalized["sampling_rate_source"] = f"normalized_from_{field}"
                return normalized

        normalized["effective_sampling_rate"] = cls._parse_sampling_rate(fallback_sampling_rate)
        normalized["sampling_rate_source"] = "fallback_sampling_rate"
        return normalized

    @staticmethod
    def _parse_sampling_rate(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            stripped_value = value.strip()
            if not stripped_value:
                return None
            try:
                return int(stripped_value)
            except ValueError:
                return None
        return None
