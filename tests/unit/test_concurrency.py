"""Concurrency tests for shared mutable state.

The LangGraph wrap means concurrent invokes can share one agent, one gateway
and one spend tracker. These tests pin that the shared objects are safe to use
from multiple threads, by widening the read-modify-write windows so the races
are deterministic rather than luck-of-the-scheduler.
"""

import threading
import time

from agent import graph as graph_module
from sentinelpay.policy.evaluator import PolicyEvaluator


def test_agent_is_built_exactly_once_under_concurrency(monkeypatch):
    """Concurrent first invokes must yield the identical agent instance."""
    real_init = graph_module.DeepAgent.__init__

    def slow_init(self, *args, **kwargs):
        time.sleep(0.2)  # widen the check-then-assign window
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(graph_module.DeepAgent, "__init__", slow_init)

    results = []

    def build():
        results.append(graph_module._build_agent())

    threads = [threading.Thread(target=build) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 8
    assert all(r is results[0] for r in results)


def test_spend_records_are_not_lost_when_prune_and_record_interleave():
    """A record that lands during a prune must not be silently dropped."""

    class SlowPruneEvaluator(PolicyEvaluator):
        def _prune(self, agent_id, window_seconds, now):
            cutoff = now - window_seconds
            entries = [
                (ts, amt)
                for ts, amt in self._spend_log.get(agent_id, [])
                if ts > cutoff
            ]
            time.sleep(0.005)  # hold the read-replace window open
            self._spend_log[agent_id] = entries
            return entries

    evaluator = SlowPruneEvaluator()
    agent_id = "agent-race-01"

    def reader():
        for _ in range(40):
            evaluator.get_cumulative_spend(agent_id)

    def recorder():
        for _ in range(40):
            evaluator.record_spend(agent_id, 1)

    t1 = threading.Thread(target=reader)
    t2 = threading.Thread(target=recorder)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert evaluator.get_cumulative_spend(agent_id) == 40