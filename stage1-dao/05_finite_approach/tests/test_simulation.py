import io
import unittest
from contextlib import redirect_stdout

import simpy

from .. import FiniteApproachSimulation, Kind


def cars(result):
    return [user for user in result.participants if user.kind is Kind.CAR]


def pedestrians(result):
    return [user for user in result.participants if user.kind is Kind.PEDESTRIAN]


def run_simulation(**kwargs):
    simulation = FiniteApproachSimulation(env=simpy.Environment(), **kwargs)
    with redirect_stdout(io.StringIO()):
        result = simulation.run()
    return simulation, result


class FiniteApproachTests(unittest.TestCase):
    def test_waits_for_later_arrivals_after_queue_drains(self):
        _, result = run_simulation(car_arrivals=[0, 120], pedestrian_arrivals=[])
        self.assertEqual([car.finished_at for car in cars(result)], [12, 132])
        self.assertEqual(result.finished_at, 132)
        self.assertEqual(result.count_finished(), 2)

    def test_car_can_finish_after_vehicle_phase_ends(self):
        simulation, result = run_simulation(car_arrivals=[9, 10], pedestrian_arrivals=[])
        self.assertEqual(
            [(car.crossing_started_at, car.crossing_finished_at) for car in cars(result)],
            [(19, 21), (30, 32)],
        )
        self.assertEqual(result.count(Kind.CAR), 2)
        self.assertEqual(result.count_finished(), 2)
        self.assertTrue(all(car.finished_at is not None for car in cars(result)))
        self.assertEqual(simulation.free_places_at_end_count, 5)

    def test_empty_input_finishes_immediately(self):
        simulation, result = run_simulation(car_arrivals=[], pedestrian_arrivals=[])
        self.assertEqual(result.finished_at, 0)
        self.assertEqual(result.count_finished(), 0)
        self.assertEqual(simulation.free_places_at_end_count, 5)

    def test_capacity_and_external_fifo(self):
        simulation, result = run_simulation(
            car_arrivals=[0] * 8,
            pedestrian_arrivals=[1, 1],
            is_pedestrian_at_crossing=True,
        )
        self.assertEqual(
            [user.entered_approach_at for user in cars(result)],
            [0, 0, 0, 0, 0, 12, 14, 16],
        )
        self.assertEqual(
            [user.crossing_started_at for user in cars(result)],
            [10, 12, 14, 16, 18, 30, 32, 34],
        )
        self.assertEqual(
            [user.crossing_started_at for user in pedestrians(result)], [20, 20]
        )
        self.assertEqual(result.finished_at, 36)
        self.assertEqual(simulation.free_places_at_end_count, 5)
        self.assertLessEqual(
            max(snapshot.approach_occupied_count for snapshot in result.monitoring), 5
        )
        self.assertEqual(result.monitoring[-1].approach_occupied_count, 0)

    def test_random_streams_return_all_approach_places(self):
        simulation, result = run_simulation(seed=7)
        self.assertGreaterEqual(result.finished_at, 600)
        self.assertTrue(
            all(user.finished_at is not None for user in result.participants)
        )
        self.assertEqual(simulation.free_places_at_end_count, 5)


if __name__ == "__main__":
    unittest.main()
