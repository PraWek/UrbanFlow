import io
import unittest
from contextlib import redirect_stdout

from .. import ParallelTravelSimulation


class ParallelTravelTests(unittest.TestCase):
    def test_processes_move_concurrently(self):
        simulation = ParallelTravelSimulation()
        output = io.StringIO()
        with redirect_stdout(output):
            simulation.run()
        self.assertEqual(
            [journey.started_at for journey in simulation.journeys], [0, 0]
        )
        self.assertEqual(
            [journey.arrived_at for journey in simulation.journeys], [10, 20]
        )

if __name__ == "__main__":
    unittest.main()
