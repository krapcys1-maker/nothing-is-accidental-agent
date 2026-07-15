"""Tests for the reproducible full-SHA pytest partition helper."""
from __future__ import annotations

import codecs
import hashlib
from pathlib import Path

from scripts import run_test_partitions


def test_partition_index_uses_the_full_sha256_digest():
    node_id = "tests/test_example.py::test_case[param]"
    expected = int.from_bytes(
        hashlib.sha256(node_id.encode("utf-8")).digest(), byteorder="big", signed=False,
    ) % 7
    assert run_test_partitions.partition_index(node_id, 7) == expected


def test_partition_cover_is_exact_once_and_order_independent():
    node_ids = [
        "tests/test_a.py::test_one",
        "tests/test_a.py::test_two",
        "tests/test_b.py::test_three[param]",
        "tests/test_c.py::test_four",
    ]
    run_test_partitions.verify_partition_cover(node_ids, parts=4)
    selected = [
        node_id
        for index in range(4)
        for node_id in run_test_partitions.select_partition(reversed(node_ids), parts=4, index=index)
    ]
    assert sorted(selected) == sorted(node_ids)
    assert len(selected) == len(set(selected))


def test_partition_runner_source_is_utf8_without_bom_and_batches_are_complete():
    source = Path(run_test_partitions.__file__)
    assert not source.read_bytes().startswith(codecs.BOM_UTF8)
    node_ids = [f"tests/test_{index}.py::test_case" for index in range(2_000)]
    batches = run_test_partitions.command_batches(node_ids)
    assert [node_id for batch in batches for node_id in batch] == node_ids
    assert all(batch for batch in batches)
