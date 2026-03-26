"""Unit tests for src/logging_config.py"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.logging_config import MetricsTracker, log_action


class TestMetricsTracker:
    def test_initial_state(self):
        tracker = MetricsTracker()
        assert tracker.total_requests == 0
        assert tracker.total_errors == 0
        assert tracker.response_times == []
        assert tracker.endpoint_stats == {}

    def test_record_request_increments_total(self):
        tracker = MetricsTracker()
        tracker.record_request("/get", 0.1, 200)
        assert tracker.total_requests == 1

    def test_record_error_increments_errors(self):
        tracker = MetricsTracker()
        tracker.record_request("/get", 0.1, 500)
        assert tracker.total_errors == 1

    def test_record_success_does_not_increment_errors(self):
        tracker = MetricsTracker()
        tracker.record_request("/get", 0.1, 200)
        assert tracker.total_errors == 0

    def test_get_metrics_returns_correct_keys(self):
        tracker = MetricsTracker()
        tracker.record_request("/get", 0.05, 200)
        m = tracker.get_metrics()
        assert "uptime_seconds" in m
        assert "total_requests" in m
        assert "total_errors" in m
        assert "error_rate_percent" in m
        assert "avg_response_time_ms" in m
        assert "endpoints" in m

    def test_get_metrics_no_requests_zero_error_rate(self):
        tracker = MetricsTracker()
        m = tracker.get_metrics()
        assert m["error_rate_percent"] == 0
        assert m["avg_response_time_ms"] == 0

    def test_reset_metrics(self):
        tracker = MetricsTracker()
        tracker.record_request("/get", 0.1, 200)
        tracker.reset_metrics()
        assert tracker.total_requests == 0

    def test_endpoint_stats_tracked(self):
        tracker = MetricsTracker()
        tracker.record_request("/api", 0.1, 200)
        tracker.record_request("/api", 0.2, 404)
        m = tracker.get_metrics()
        assert "/api" in m["endpoints"]
        assert m["endpoints"]["/api"]["count"] == 2


class TestLogAction:
    def test_log_action_success_path(self):
        @log_action("test_operation")
        def my_func(x):
            return x * 2

        result = my_func(5)
        assert result == 10

    def test_log_action_failure_path(self):
        @log_action("test_operation")
        def failing_func():
            raise ValueError("intentional error")

        with pytest.raises(ValueError, match="intentional error"):
            failing_func()

    def test_log_action_preserves_function_name(self):
        @log_action("test_operation")
        def named_function():
            return "ok"

        assert named_function.__name__ == "named_function"

    def test_log_action_passes_args(self):
        @log_action("test_operation")
        def add(a, b, c=0):
            return a + b + c

        assert add(1, 2, c=3) == 6
