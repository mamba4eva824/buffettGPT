"""
Metrics collection and reporting for performance tests.

Tracks latencies per named metric and computes percentiles, throughput,
and error rates for inclusion in test reports.
"""

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

import numpy as np


class MetricsCollector:
    """Collect timing samples and compute summary statistics.

    Usage::

        mc = MetricsCollector()
        mc.record('webhook_processing', 12.5)
        mc.record('webhook_processing', 14.1)
        mc.record_error('webhook_processing')
        report = mc.generate_report()
    """

    def __init__(self) -> None:
        self._samples: Dict[str, List[float]] = defaultdict(list)
        self._errors: Dict[str, int] = defaultdict(int)
        self._start_time: float = time.monotonic()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, name: str, duration_ms: float) -> None:
        """Record a successful operation duration in milliseconds."""
        self._samples[name].append(duration_ms)

    def record_error(self, name: str) -> None:
        """Record a failed operation."""
        self._errors[name] += 1

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_percentiles(self, name: str) -> Dict[str, Optional[float]]:
        """Return p50, p95, p99 for the given metric.

        Returns ``None`` values if no samples have been recorded.
        """
        samples = self._samples.get(name)
        if not samples:
            return {'p50': None, 'p95': None, 'p99': None}

        arr = np.array(samples)
        return {
            'p50': float(np.percentile(arr, 50)),
            'p95': float(np.percentile(arr, 95)),
            'p99': float(np.percentile(arr, 99)),
        }

    def get_throughput(self) -> float:
        """Return overall requests per second across all metrics."""
        elapsed = time.monotonic() - self._start_time
        if elapsed <= 0:
            return 0.0
        total = sum(len(v) for v in self._samples.values())
        return total / elapsed

    def get_error_rate(self, name: Optional[str] = None) -> float:
        """Return error rate as a fraction (0.0 – 1.0).

        If *name* is ``None``, returns the aggregate rate across all metrics.
        """
        if name:
            successes = len(self._samples.get(name, []))
            errors = self._errors.get(name, 0)
        else:
            successes = sum(len(v) for v in self._samples.values())
            errors = sum(self._errors.values())

        total = successes + errors
        if total == 0:
            return 0.0
        return errors / total

    @property
    def metric_names(self) -> List[str]:
        """Return all recorded metric names."""
        return sorted(set(self._samples.keys()) | set(self._errors.keys()))

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_report(self) -> Dict[str, Any]:
        """Generate a summary report dict.

        Returns a dict with per-metric percentiles plus aggregate
        throughput (rps) and error_rate.
        """
        elapsed = time.monotonic() - self._start_time
        total_success = sum(len(v) for v in self._samples.values())
        total_errors = sum(self._errors.values())
        total = total_success + total_errors

        report: Dict[str, Any] = {
            'elapsed_seconds': round(elapsed, 3),
            'total_requests': total,
            'total_errors': total_errors,
            'rps': round(total_success / elapsed, 2) if elapsed > 0 else 0.0,
            'error_rate': round(total_errors / total, 4) if total > 0 else 0.0,
            'metrics': {},
        }

        for name in self.metric_names:
            samples = self._samples.get(name, [])
            pcts = self.get_percentiles(name)
            report['metrics'][name] = {
                'count': len(samples),
                'errors': self._errors.get(name, 0),
                'p50': round(pcts['p50'], 3) if pcts['p50'] is not None else None,
                'p95': round(pcts['p95'], 3) if pcts['p95'] is not None else None,
                'p99': round(pcts['p99'], 3) if pcts['p99'] is not None else None,
                'min': round(min(samples), 3) if samples else None,
                'max': round(max(samples), 3) if samples else None,
                'mean': round(float(np.mean(samples)), 3) if samples else None,
            }

        return report
