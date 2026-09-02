"""Pytest configuration."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration-ada",
        action="store_true",
        default=False,
        help="Run live integration tests against ada AO engine",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-integration-ada"):
        return
    skip = pytest.mark.skip(reason="need --run-integration-ada")
    for item in items:
        if "integration_ada" in item.keywords:
            item.add_marker(skip)
