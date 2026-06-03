from apps.monitor.services.flow_sampling import FlowSamplingService


def test_normalize_payload_prefers_reported_effective_sampling_rate():
    result = FlowSamplingService.normalize_payload(
        {
            "effective_sampling_rate": 256,
            "SAMPLING_INTERVAL": 1024,
            "sampling_rate": 2048,
        },
        fallback_sampling_rate=4096,
    )

    assert result["effective_sampling_rate"] == 256
    assert result["sampling_rate_source"] == "reported_effective_sampling_rate"


def test_normalize_payload_uses_first_non_empty_candidate_field():
    result = FlowSamplingService.normalize_payload(
        {
            "SAMPLING_INTERVAL": "",
            "SAMPLING_ALGORITHM": 512,
            "sampling_rate": 1024,
            "samplingRate": 2048,
        },
        fallback_sampling_rate=4096,
    )

    assert result["effective_sampling_rate"] == 512
    assert result["sampling_rate_source"] == "normalized_from_SAMPLING_ALGORITHM"


def test_normalize_payload_coerces_sampling_values_to_integers():
    result = FlowSamplingService.normalize_payload(
        {
            "samplingRate": "2048",
        },
        fallback_sampling_rate="4096",
    )

    assert result["effective_sampling_rate"] == 2048
    assert result["sampling_rate_source"] == "normalized_from_samplingRate"


def test_normalize_payload_falls_back_to_asset_sampling_rate():
    result = FlowSamplingService.normalize_payload({}, fallback_sampling_rate=4096)

    assert result["effective_sampling_rate"] == 4096
    assert result["sampling_rate_source"] == "fallback_sampling_rate"
