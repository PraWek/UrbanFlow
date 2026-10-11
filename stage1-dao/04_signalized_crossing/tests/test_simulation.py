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
        simulation = SignalizedCrossingSimulation(**kwargs, env=simpy.Environment())
        return simulation.run()


class SignalizedCrossingTests(unittest.TestCase):
    def test_empty_input_finishes_immediately(self):
        result = run_simulation(car_arrivals=[], pedestrian_arrivals=[])
        self.assertEqual(result.finished_at, 0)
        self.assertEqual(result.count_finished(), 0)

    def test_waits_for_later_arrivals_after_queue_drains(self):
        result = run_simulation(car_arrivals=[0, 120], pedestrian_arrivals=[])
        self.assertEqual([car.crossing_finished_at for car in cars(result)], [12, 132])
        self.assertEqual(result.finished_at, 132)
        self.assertEqual(result.count_finished(), 2)

    def test_fifo_and_pedestrian_group(self):
        result = run_simulation(car_arrivals=[0, 0, 0], pedestrian_arrivals=[1, 1])
        self.assertEqual(
            [(user.crossing_started_at, user.crossing_finished_at) for user in cars(result)],
            [(10, 12), (12, 14), (14, 16)],
        )
        self.assertEqual(
            [(user.crossing_started_at, user.crossing_finished_at) for user in pedestrians(result)],
            [(50, 55), (50, 55)],
        )

    def test_phase_boundary_is_rechecked(self):
        result = run_simulation(car_arrivals=[18, 19], pedestrian_arrivals=[1, 20, 21])
        self.assertEqual([user.crossing_started_at for user in cars(result)], [30, 32])
        self.assertEqual([user.crossing_started_at for user in pedestrians(result)], [50, 50, 50])

    def test_car_can_finish_after_vehicle_phase_ends(self):
        result = run_simulation(car_arrivals=[9, 10], pedestrian_arrivals=[])
        self.assertEqual(
            [(car.crossing_started_at, car.crossing_finished_at) for car in cars(result)],
            [(19, 21), (30, 32)],
        )

    def test_random_streams_are_fully_drained(self):
        result = run_simulation(seed=7)
        self.assertGreaterEqual(result.finished_at, 600)
        self.assertTrue(all(user.crossing_finished_at is not None for user in result.participants))


if __name__ == "__main__":
    unittest.main()
