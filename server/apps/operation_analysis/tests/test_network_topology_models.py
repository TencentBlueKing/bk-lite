# -*- coding: utf-8 -*-
"""
Tests for :class:`apps.operation_analysis.models.models.NetworkTopology`.

Covers:

* Token storage round-trip — the plaintext is encrypted, the read API only
  exposes ``token_set``.
* URL normalisation (``base_url`` must start with http(s) and lose trailing
  slashes; design.md §6.1).
* ``view_sets`` structural validation — node uniqueness, port-pair count
  on saved links, link node references, cascade semantics on remove
  (design.md §6.5 / spec "Cascade delete handled in application layer").
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.operation_analysis.models.models import Directory, NetworkTopology, decrypt_weops_token, encrypt_weops_token
from apps.operation_analysis.services.network_topology import canvas_config


def _make_directory():
    return Directory.objects.create(name="网络拓扑目录", groups=[1])


def _make_topology(**overrides):
    directory = _make_directory()
    defaults = {
        "name": "核心网拓扑",
        "directory": directory,
        "groups": [1],
        "base_url": "https://weops.example.com",
        "token": "service-token",
    }
    defaults.update(overrides)
    return NetworkTopology.objects.create(**defaults)


# --------------------------------------------------------------------------- #
# Token / URL handling                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_token_is_encrypted_on_save_and_round_trips():
    topology = _make_topology(token="plain-token")
    topology.refresh_from_db()

    assert topology.token != "plain-token"
    assert decrypt_weops_token(topology.token) == "plain-token"
    assert topology.token_set() is True
    assert topology.decrypt_token() == "plain-token"


@pytest.mark.django_db
def test_empty_token_persists_as_empty_string_not_encrypted_garbage():
    topology = _make_topology(token="")
    topology.refresh_from_db()
    assert topology.token == ""
    assert topology.token_set() is False


@pytest.mark.django_db
def test_normalize_base_url_strips_trailing_slashes_and_validates_prefix():
    assert NetworkTopology.normalize_base_url("https://weops.example.com/") == "https://weops.example.com"
    assert NetworkTopology.normalize_base_url("http://weops/path///") == "http://weops/path"
    with pytest.raises(DjangoValidationError):
        NetworkTopology.normalize_base_url("ftp://weops")
    with pytest.raises(DjangoValidationError):
        NetworkTopology.normalize_base_url("weops.example.com")


@pytest.mark.django_db
def test_save_normalizes_base_url_persisted_to_db():
    topology = _make_topology(base_url="https://weops.example.com/api///")
    topology.refresh_from_db()
    assert topology.base_url == "https://weops.example.com/api"


# --------------------------------------------------------------------------- #
# view_sets validation                                                         #
# --------------------------------------------------------------------------- #


def _node_payload(node_id="node-1", bk_obj_id="bk_switch", bk_inst_id=10001, **extras):
    payload = {
        "id": node_id,
        "bk_obj_id": bk_obj_id,
        "bk_inst_id": bk_inst_id,
        "bk_inst_name": f"{bk_obj_id}-{bk_inst_id}",
        "ip_addr": "10.0.0.1",
        "network_collect_task_id": 12,
        "network_collect_instance_id": 345,
        "plugin_group_id": 3,
        "plugin_template_id": "cisco_c9300",
        "position": {"x": 100, "y": 100},
        "style": {},
        "metrics": [],
    }
    payload.update(extras)
    return payload


def _link_payload(
    link_id="link-1",
    source="node-1",
    target="node-2",
    port_pairs=None,
    is_draft=False,
    **extras,
):
    default_pairs = [
        {
            "source_interface": {"bk_obj_id": "bk_interface", "bk_inst_id": 90001, "interface_name": "GigE0/1"},
            "target_interface": {"bk_obj_id": "bk_interface", "bk_inst_id": 90002, "interface_name": "GigE0/1"},
        }
    ]
    payload = {
        "id": link_id,
        "source_node_id": source,
        "target_node_id": target,
        "port_pairs": port_pairs if port_pairs is not None else default_pairs,
        "style": {},
        "is_draft": is_draft,
    }
    payload.update(extras)
    return payload


@pytest.mark.django_db
def test_clean_view_sets_accepts_minimal_payload():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [_node_payload("node-1"), _node_payload("node-2", "bk_router", 10002)],
        "links": [_link_payload("link-1", "node-1", "node-2")],
    }

    cleaned = topology.clean_view_sets()

    assert cleaned["nodes"][0]["bk_obj_id"] == "bk_switch"
    assert cleaned["links"][0]["source_node_id"] == "node-1"


@pytest.mark.django_db
def test_clean_view_sets_accepts_link_interface_metrics():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [_node_payload("node-1"), _node_payload("node-2", "bk_router", 10002)],
        "links": [
            _link_payload(
                "link-1",
                "node-1",
                "node-2",
                interface_metrics=["ifInOctets_5min", "ifOutOctets_5min"],
            )
        ],
    }

    cleaned = topology.clean_view_sets()

    assert cleaned["links"][0]["interface_metrics"] == ["ifInOctets_5min", "ifOutOctets_5min"]


@pytest.mark.django_db
def test_clean_view_sets_rejects_unknown_link_interface_metric():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [_node_payload("node-1"), _node_payload("node-2", "bk_router", 10002)],
        "links": [
            _link_payload(
                "link-1",
                "node-1",
                "node-2",
                interface_metrics=["ifInOctets_5min", "custom_metric"],
            )
        ],
    }

    with pytest.raises(DjangoValidationError) as exc:
        topology.clean_view_sets()

    detail = exc.value.message_dict if hasattr(exc.value, "message_dict") else exc.value.messages
    joined = " ".join(str(item) for items in detail.values() for item in items)
    assert "custom_metric" in joined


@pytest.mark.django_db
def test_clean_view_sets_rejects_duplicate_node_id():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [_node_payload("node-1"), _node_payload("node-1", "bk_router", 10002)],
        "links": [],
    }
    with pytest.raises(DjangoValidationError) as exc:
        topology.clean_view_sets()
    detail = exc.value.message_dict if hasattr(exc.value, "message_dict") else exc.value.messages
    joined = " ".join(str(item) for items in detail.values() for item in items)
    assert "id" in joined and "重复" in joined


@pytest.mark.django_db
def test_clean_view_sets_rejects_duplicate_asset_within_canvas():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [
            _node_payload("node-1"),
            _node_payload("node-2", "bk_switch", 10001),
        ],
        "links": [],
    }
    with pytest.raises(DjangoValidationError) as exc:
        topology.clean_view_sets()
    detail = exc.value.message_dict if hasattr(exc.value, "message_dict") else exc.value.messages
    joined = " ".join(str(item) for items in detail.values() for item in items)
    assert "重复" in joined and "(bk_switch, 10001)" in joined


@pytest.mark.django_db
def test_clean_view_sets_rejects_link_with_no_port_pairs():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [_node_payload("node-1"), _node_payload("node-2", "bk_router", 10002)],
        "links": [_link_payload("link-1", port_pairs=[])],
    }
    with pytest.raises(DjangoValidationError) as exc:
        topology.clean_view_sets()
    detail = exc.value.message_dict if hasattr(exc.value, "message_dict") else exc.value.messages
    joined = " ".join(str(item) for items in detail.values() for item in items)
    assert "1 对端口" in joined


@pytest.mark.django_db
def test_clean_view_sets_allows_draft_link_with_no_port_pairs():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [_node_payload("node-1"), _node_payload("node-2", "bk_router", 10002)],
        "links": [_link_payload("link-1", port_pairs=[], is_draft=True)],
    }
    # No exception expected.
    cleaned = topology.clean_view_sets()
    assert cleaned["links"][0]["is_draft"] is True


@pytest.mark.django_db
def test_clean_view_sets_rejects_link_pointing_to_missing_node():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [_node_payload("node-1")],
        "links": [_link_payload("link-1", source="node-1", target="ghost-node")],
    }
    with pytest.raises(DjangoValidationError) as exc:
        topology.clean_view_sets()
    detail = exc.value.message_dict if hasattr(exc.value, "message_dict") else exc.value.messages
    joined = " ".join(str(item) for items in detail.values() for item in items)
    assert "ghost-node" in joined


@pytest.mark.django_db
def test_clean_view_sets_rejects_duplicate_link_id():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [_node_payload("node-1"), _node_payload("node-2", "bk_router", 10002)],
        "links": [
            _link_payload("link-1", source="node-1", target="node-2"),
            _link_payload("link-1", source="node-2", target="node-1"),
        ],
    }

    with pytest.raises(DjangoValidationError) as exc:
        topology.clean_view_sets()

    detail = exc.value.message_dict if hasattr(exc.value, "message_dict") else exc.value.messages
    joined = " ".join(str(item) for items in detail.values() for item in items)
    assert "link-1" in joined
    assert "重复" in joined


@pytest.mark.django_db
def test_clean_view_sets_rejects_metric_missing_required_fields():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [
            _node_payload(
                "node-1",
                metrics=[{"metric_field": "", "result_table_id": "snmp_network"}],
            )
        ],
        "links": [],
    }
    with pytest.raises(DjangoValidationError) as exc:
        topology.clean_view_sets()
    detail = exc.value.message_dict if hasattr(exc.value, "message_dict") else exc.value.messages
    joined = " ".join(str(item) for items in detail.values() for item in items)
    assert "metric_field" in joined


@pytest.mark.django_db
def test_clean_view_sets_rejects_threshold_missing_color():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [
            _node_payload(
                "node-1",
                metrics=[
                    {
                        "metric_field": "ifHCInOctets",
                        "result_table_id": "snmp_network",
                        "thresholds": [{"value": 0}],
                    }
                ],
            )
        ],
        "links": [],
    }
    with pytest.raises(DjangoValidationError) as exc:
        topology.clean_view_sets()
    detail = exc.value.message_dict if hasattr(exc.value, "message_dict") else exc.value.messages
    joined = " ".join(str(item) for items in detail.values() for item in items)
    assert "color" in joined


@pytest.mark.django_db
def test_clean_view_sets_rejects_port_pair_missing_interface():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [_node_payload("node-1"), _node_payload("node-2", "bk_router", 10002)],
        "links": [
            _link_payload(
                "link-1",
                port_pairs=[{"source_interface": {}, "target_interface": {"bk_obj_id": "bk_interface", "bk_inst_id": 90002}}],
            )
        ],
    }
    with pytest.raises(DjangoValidationError) as exc:
        topology.clean_view_sets()
    detail = exc.value.message_dict if hasattr(exc.value, "message_dict") else exc.value.messages
    joined = " ".join(str(item) for items in detail.values() for item in items)
    assert "源接口" in joined


# --------------------------------------------------------------------------- #
# cascade_remove_node / cascade_remove_link helpers                            #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_cascade_remove_node_removes_referencing_links_too():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [
            _node_payload("node-1"),
            _node_payload("node-2", "bk_router", 10002),
            _node_payload("node-3", "bk_firewall", 10003),
        ],
        "links": [
            _link_payload("link-a", "node-1", "node-2"),
            _link_payload("link-b", "node-1", "node-3"),
            _link_payload("link-c", "node-2", "node-3"),
        ],
    }
    topology.save()

    canvas_config.cascade_remove_node(topology, "node-1")

    topology.refresh_from_db()
    payload = canvas_config.dump(topology)
    node_ids = [n["id"] for n in payload["nodes"]]
    link_ids = [link["id"] for link in payload["links"]]

    assert "node-1" not in node_ids
    assert "link-a" not in link_ids
    assert "link-b" not in link_ids
    assert "link-c" in link_ids  # only links touching node-1 are cascaded


@pytest.mark.django_db
def test_cascade_remove_node_is_idempotent_for_missing_node():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [_node_payload("node-1")],
        "links": [],
    }
    topology.save()
    canvas_config.cascade_remove_node(topology, "ghost")
    topology.refresh_from_db()
    assert [n["id"] for n in canvas_config.dump(topology)["nodes"]] == ["node-1"]


@pytest.mark.django_db
def test_cascade_remove_link_removes_only_target_link():
    topology = _make_topology(token="t")
    topology.view_sets = {
        "nodes": [
            _node_payload("node-1"),
            _node_payload("node-2", "bk_router", 10002),
        ],
        "links": [
            _link_payload("link-a", "node-1", "node-2"),
            _link_payload("link-b", "node-1", "node-2"),
        ],
    }
    topology.save()

    canvas_config.cascade_remove_link(topology, "link-a")

    topology.refresh_from_db()
    link_ids = [link["id"] for link in canvas_config.dump(topology)["links"]]
    assert link_ids == ["link-b"]


# --------------------------------------------------------------------------- #
# round-trip the encryption helpers                                             #
# --------------------------------------------------------------------------- #


def test_encrypt_weops_token_round_trip():
    raw = "raw-token-123"
    encrypted = encrypt_weops_token(raw)
    assert encrypted != raw
    assert decrypt_weops_token(encrypted) == raw


def test_encrypt_weops_token_handles_empty_input():
    assert encrypt_weops_token("") in ("", None)
    assert encrypt_weops_token(None) is None
