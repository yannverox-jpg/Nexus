import unittest
import time
from advanced_resilience import CircuitBreaker, CircuitBreakerOpenException, SystemState, AdvancedNexusCore

class TestAdvancedResilience(unittest.TestCase):

    def test_circuit_breaker_success(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_time=1.0)
        func = lambda x: x * 2
        res = cb(func, 5)
        self.assertEqual(res, 10)
        self.assertEqual(cb.state, "CLOSED")

    def test_circuit_breaker_opens_after_failures(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_time=1.0)

        def failing_func():
            raise ValueError("API Error")

        # First failure
        with self.assertRaises(ValueError):
            cb(failing_func)
        self.assertEqual(cb.state, "CLOSED")

        # Second failure -> opens circuit
        with self.assertRaises(ValueError):
            cb(failing_func)
        self.assertEqual(cb.state, "OPEN")

        # Subsequent call while open raises CircuitBreakerOpenException
        with self.assertRaises(CircuitBreakerOpenException):
            cb(failing_func)

    def test_circuit_breaker_half_open_recovery(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_time=0.1)

        def failing_func():
            raise ValueError("API Error")

        with self.assertRaises(ValueError):
            cb(failing_func)
        self.assertEqual(cb.state, "OPEN")

        time.sleep(0.15)

        # Recovery call
        success_func = lambda: "OK"
        res = cb(success_func)
        self.assertEqual(res, "OK")
        self.assertEqual(cb.state, "CLOSED")

    def test_advanced_nexus_core_pipeline(self):
        core = AdvancedNexusCore()
        core.process_pipeline()
        self.assertEqual(core.state, SystemState.IDLE)

if __name__ == "__main__":
    unittest.main()
