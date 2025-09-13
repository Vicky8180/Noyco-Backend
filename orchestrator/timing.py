# orchestrator/timing.py
"""
Utilities for tracking execution time of different operations.
"""

import time
from collections import defaultdict

class TimingMetrics:
    """Helper class to track execution time of different steps"""
    def __init__(self):
        self.metrics = defaultdict(float)
        self.start_times = {}

    def start(self, step_name: str):
        """Start timing a step"""
        self.start_times[step_name] = time.time()

    def end(self, step_name: str):
        """End timing a step and record duration"""
        if step_name in self.start_times:
            duration = time.time() - self.start_times[step_name]
            self.metrics[step_name] = round(duration * 1000, 2)  # Convert to milliseconds
            del self.start_times[step_name]

    def get_metrics(self):
        """Get all collected metrics"""
        return dict(self.metrics)
