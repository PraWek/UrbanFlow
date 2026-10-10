import io
import unittest
from contextlib import redirect_stdout

import simpy

from .. import DownstreamSpillbackSimulation, Kind


def cars(result):
    return [user for user in result.participants if user.kind is Kind.CAR]


def pedestrians(result):
    return [user for user in result.participants if user.kind is Kind.PEDESTRIAN]


def run_simulation(**kwargs):
    simulation = DownstreamSpillbackSimulation(
        env=simpy.Environment(),
        **kwargs,
    )
    with redirect_stdout(io.StringIO()):
        result = simulation.run()
    return simulation, result


class DownstreamSpillbackTests(unittest.TestCase):
    def test_closed_exit_blocks_after_five_reservations(self):
        simulation, result = run_simulation(
            car_arrivals=[0] * 8,
            pedestrian_arrivals=[1, 1],
            cars_at_stop_line=True,
            pedestrians_at_crossing=True,
            exit_blocked_until=60,
        )
        self.assertEqual(
            [user.crossing_started_at for user in cars(result)],
            [0, 2, 4, 6, 8, 60, 62, 64],
        )
        self.assertEqual(
            [user.finished_at for user in cars(result)[:5]], [60] * 5
        )
        self.assertEqual(
            [user.crossing_started_at for user in pedestrians(result)], [20, 20]
        )
        self.assertGreater(cars(result)[5].downstream_blocked_time, 0)
        self.assertLessEqual(
            max(row["downstream_used"] for row in result.monitoring), 5
        )
        self.assertEqual(result.monitoring[-1]["downstream_used"], 0)
        self.assertEqual(simulation.free_places_at_end, 5)

    def test_identical_input_streams_for_open_and_blocked_exit(self):
        _, opened = run_simulation(seed=7)
        _, blocked = run_simulation(
            seed=7, exit_blocked_until=60
        )
        self.assertEqual(
            [
                (user.id, user.appeared_at)
                for user in opened.participants
            ],
            [
                (user.id, user.appeared_at)
                for user in blocked.participants
            ],
        )


if __name__ == "__main__":
    unittest.main()
