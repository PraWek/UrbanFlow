import io
import unittest
from contextlib import redirect_stdout

from .. import TrafficLightSimulation


class TrafficLightTests(unittest.TestCase):
    def test_exact_three_cycles(self):
        output = io.StringIO()
        with redirect_stdout(output):
            TrafficLightSimulation().run()
        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "time=0, color=green",
                "time=30, color=yellow",
                "time=35, color=red",
                "time=60, color=green",
                "time=90, color=yellow",
                "time=95, color=red",
                "time=120, color=green",
                "time=150, color=yellow",
                "time=155, color=red",
            ],
        )


if __name__ == "__main__":
    unittest.main()
