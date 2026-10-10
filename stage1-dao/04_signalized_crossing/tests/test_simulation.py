import io
import unittest
from contextlib import redirect_stdout

import simpy

from .. import Kind, SignalizedCrossingSimulation


def cars(result):
    return [p for p in result.participants if p.kind is Kind.CAR]


def pedestrians(result):
    return [p for p in result.participants if p.kind is Kind.PEDESTRIAN]


def run_simulation(**kwargs):
    with redirect_stdout(io.StringIO()):
        simulation = SignalizedCrossingSimulation(
            **kwargs,
            env=simpy.Environment(),
        )
        return simulation.run()


class SignalizedCrossingTests(unittest.TestCase):
    def test_fifo_and_pedestrian_group(self):
        result = run_simulation(
            car_arrivals=[0, 0, 0],
            pedestrian_arrivals=[1, 1],
        )
        self.assertEqual(
            [
                (user.crossing_started_at, user.crossing_finished_at)
                for user in cars(result)
            ],
            [(10, 12), (12, 14), (14, 16)],
        )
        self.assertEqual(
            [
                (user.crossing_started_at, user.crossing_finished_at)
                for user in pedestrians(result)
            ],
            [(50, 55), (50, 55)],
        )

    def test_phase_boundary_is_rechecked(self):
        result = run_simulation(
            car_arrivals=[18, 19],
            pedestrian_arrivals=[1, 20, 21],
        )
        self.assertEqual(
            [user.crossing_started_at for user in cars(result)], [30, 32]
        )
        self.assertEqual(
            [user.crossing_started_at for user in pedestrians(result)],
            [50, 50, 50],
        )

    def test_random_streams_are_fully_drained(self):
        result = run_simulation(seed=7)
        self.assertGreaterEqual(result.finished_at, 600)
        self.assertTrue(
            all(
                user.crossing_finished_at is not None
                for user in result.participants
            )
        )


if __name__ == "__main__":
    unittest.main()
