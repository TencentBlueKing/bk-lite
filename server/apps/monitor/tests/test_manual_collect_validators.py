"""manual_collect 视图层校验函数规格测试（纯函数）。"""

import pytest

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.monitor.views import manual_collect as mc


class TestValidateIntegerField:
    def test_none_raises(self):
        with pytest.raises(ValidationAppException):
            mc._validate_integer_field("f", None)

    def test_bool_raises(self):
        with pytest.raises(ValidationAppException):
            mc._validate_integer_field("f", True)

    def test_int_ok(self):
        assert mc._validate_integer_field("f", 5) == 5

    def test_numeric_string(self):
        assert mc._validate_integer_field("f", " 7 ") == 7

    def test_empty_string_raises(self):
        with pytest.raises(ValidationAppException):
            mc._validate_integer_field("f", "  ")

    def test_non_numeric_string_raises(self):
        with pytest.raises(ValidationAppException):
            mc._validate_integer_field("f", "abc")

    def test_other_type_raises(self):
        with pytest.raises(ValidationAppException):
            mc._validate_integer_field("f", [1])


class TestValidateFlowIdentityField:
    def test_int_fields_delegate(self):
        assert mc._validate_flow_identity_field("cloud_region_id", "3") == 3

    def test_ip_valid(self):
        assert mc._validate_flow_identity_field("ip", " 10.0.0.1 ") == "10.0.0.1"

    def test_ip_invalid(self):
        with pytest.raises(ValidationAppException):
            mc._validate_flow_identity_field("ip", "not-ip")

    def test_ip_empty(self):
        with pytest.raises(ValidationAppException):
            mc._validate_flow_identity_field("ip", "")

    def test_other_field_passthrough(self):
        assert mc._validate_flow_identity_field("foo", "bar") == "bar"


class TestValidateProtocol:
    def test_invalid(self):
        with pytest.raises(ValidationAppException):
            mc._validate_protocol("protocol", "bogus")

    def test_valid(self):
        proto = next(iter(mc.SUPPORTED_FLOW_PROTOCOLS))
        assert mc._validate_protocol("protocol", proto) == proto


class TestValidateName:
    def test_non_string(self):
        with pytest.raises(ValidationAppException):
            mc._validate_name("name", 1)

    def test_empty(self):
        with pytest.raises(ValidationAppException):
            mc._validate_name("name", "  ")

    def test_trims(self):
        assert mc._validate_name("name", "  abc ") == "abc"


class TestValidateTimeWindow:
    def test_valid(self):
        assert mc._validate_time_window("w", "5m") == "5m"

    def test_invalid_format(self):
        with pytest.raises(ValidationAppException):
            mc._validate_time_window("w", "5x")


class TestValidateFallbackSamplingRate:
    def test_bool_raises(self):
        with pytest.raises(ValidationAppException):
            mc._validate_fallback_sampling_rate("f", True)

    def test_int_ok(self):
        assert mc._validate_fallback_sampling_rate("f", 10) == 10

    def test_string_ok(self):
        assert mc._validate_fallback_sampling_rate("f", " 5 ") == 5

    def test_negative_raises(self):
        with pytest.raises(ValidationAppException):
            mc._validate_fallback_sampling_rate("f", -1)

    def test_invalid_string(self):
        with pytest.raises(ValidationAppException):
            mc._validate_fallback_sampling_rate("f", "abc")


class TestValidateOrganizations:
    def test_not_list_raises(self):
        with pytest.raises(ValidationAppException):
            mc._validate_organizations("o", "x")

    def test_normalizes_and_dedups(self):
        assert mc._validate_organizations("o", [1, "2", 1]) == [1, 2]

    def test_bool_raises(self):
        with pytest.raises(ValidationAppException):
            mc._validate_organizations("o", [True])

    def test_invalid_string_raises(self):
        with pytest.raises(ValidationAppException):
            mc._validate_organizations("o", ["abc"])


class TestNormalizeRequestPayloadMapping:
    def test_plain_dict(self):
        assert mc._normalize_request_payload_mapping({"a": 1}, multi_value_fields=set()) == {"a": 1}

    def test_getlist_for_multi_fields(self):
        class FakeQD:
            def __init__(self, data):
                self._d = data
            def keys(self):
                return self._d.keys()
            def getlist(self, k):
                return self._d[k]
            def get(self, k):
                return self._d[k][0]

        qd = FakeQD({"orgs": [1, 2], "name": ["x"]})
        out = mc._normalize_request_payload_mapping(qd, multi_value_fields={"orgs"})
        assert out["orgs"] == [1, 2]
        assert out["name"] == "x"


class TestValidatedRequestPayload:
    def test_non_mapping_raises(self):
        with pytest.raises(ValidationAppException):
            mc._validated_request_payload("notdict", required_fields=set(), optional_fields=set())

    def test_unknown_field_raises(self):
        with pytest.raises(ValidationAppException):
            mc._validated_request_payload(
                {"x": 1}, required_fields=set(), optional_fields=set(),
            )

    def test_missing_required_raises(self):
        with pytest.raises(ValidationAppException):
            mc._validated_request_payload(
                {}, required_fields={"name"}, optional_fields=set(),
            )

    def test_applies_validators_and_filters(self):
        out = mc._validated_request_payload(
            {"name": " x ", "extra_opt": "keep"},
            required_fields={"name"},
            optional_fields={"extra_opt"},
            field_validators={"name": mc._validate_name},
        )
        assert out == {"name": "x", "extra_opt": "keep"}
