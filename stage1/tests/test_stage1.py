import unittest

from stage1 import exercise01, exercise02, exercise03, exercise04, exercise05, exercise06, exercise07
from stage1.data import Arrival
from stage1.model import CAPACITIES, LOCAL_WINDOWS, StreetModel


def cars(result, route=None):
    return [p for p in result.records if p.kind == "car" and not p.initial
            and (route is None or p.route == route)]


def pedestrians(result):
    return [p for p in result.records if p.kind == "pedestrian"]


class Stage1Tests(unittest.TestCase):
    def assert_complete(self, result):
        self.assertTrue(all(p.exited is not None for p in result.records))
        self.assertTrue(all(p.exited <= result.finished_at for p in result.records))
        self.assertEqual(len({p.id for p in result.records}), len(result.records))
        for metrics in (result.summary()["car"], result.summary()["pedestrian"]):
            self.assertEqual(metrics["created"], metrics["completed"])

    def assert_traffic_rules(self, result):
        multi = result.exercise == 7
        windows = {"straight": (0, 24), "left": (24, 36), "right": (36, 48)}
        for p in cars(result):
            position = p.start % (60 if multi else 30)
            begin, end = windows[p.route] if multi else (0, 20)
            self.assertGreaterEqual(position, begin)
            self.assertLess(position, end)
            self.assertLessEqual(position + 2, end)
            self.assertAlmostEqual(p.end - p.start, 2)
            self.assertGreaterEqual(p.start, p.queued)
            if multi:
                begin, end = LOCAL_WINDOWS[p.route]
                self.assertGreaterEqual(p.start_b % 60, begin)
                self.assertLessEqual(p.start_b % 60 + 2, end)
                self.assertAlmostEqual(p.arrived_b, p.end + 10)
                self.assertAlmostEqual(p.exited, p.start_b + 2)
        for p in pedestrians(result):
            self.assertEqual(p.start % (60 if multi else 30), 48 if multi else 20)
            self.assertLess(p.queued, p.start)
            self.assertEqual(p.end - p.start, 5)
            for car in cars(result):
                self.assertFalse(car.start < p.end and p.start < car.end,
                                 f"Конфликт на переходе: {car.id}, {p.id}")
        for route in ("straight", "left", "right"):
            route_cars = cars(result, route)
            expected = sorted(route_cars, key=lambda p: (p.queued, p.id))
            actual = sorted(route_cars, key=lambda p: p.start)
            self.assertEqual([p.id for p in expected], [p.id for p in actual])
            for previous, current in zip(actual, actual[1:]):
                self.assertLessEqual(previous.end, current.start)
            if multi:
                local_order = sorted(route_cars, key=lambda p: p.start_b)
                self.assertEqual([p.id for p in actual], [p.id for p in local_order])
        for row in result.monitoring:
            for key, value in row.items():
                if key != "time":
                    self.assertGreaterEqual(value, 0, key)
            if result.exercise == 5:
                self.assertLessEqual(row["a_occupied"], 5)
            for route, capacity in (CAPACITIES if multi else {"straight": 5}).items():
                key = f"b_{route}_used"
                if key in row:
                    self.assertLessEqual(row[key], capacity)
                    self.assertEqual(row[key], row[f"b_{route}_occupied"]
                                     + row[f"b_{route}_reserved"])

    def test_exercise1_exact_log(self):
        result = exercise01.run()
        self.assertEqual([(r["time"], r["color"]) for r in result.events], [
            (0, "green"), (30, "yellow"), (35, "red"),
            (60, "green"), (90, "yellow"), (95, "red"),
            (120, "green"), (150, "yellow"), (155, "red"),
        ])
        self.assertEqual(result.finished_at, 180)

    def test_exercise2_concurrent_travel(self):
        result = exercise02.run()
        self.assertEqual([p.appeared for p in result.records], [0, 0])
        self.assertEqual([p.exited for p in result.records], [10, 20])
        self.assertEqual(result.finished_at, 20)

    def test_exercise3_reproducibility_and_drain(self):
        result = exercise03.run(42)
        self.assertEqual(result, exercise03.run(42))
        self.assertNotEqual(result.events, exercise03.run(43).events)
        self.assert_complete(result)
        for p in result.records:
            self.assertGreater(p.appeared, 0)
            self.assertLess(p.appeared, 600)
            self.assertAlmostEqual(p.exited - p.appeared, 10 if p.kind == "car" else 20)
        self.assertGreater(result.finished_at, 600)

    def test_exercise4_table(self):
        result = exercise04.demo()
        self.assertEqual([(p.start, p.end) for p in cars(result)], [(0, 2), (2, 4), (4, 6)])
        self.assertEqual([(p.start, p.end) for p in pedestrians(result)], [(20, 25)] * 2)
        self.assert_traffic_rules(result)
        self.assert_complete(result)

    def test_boundaries_and_pedestrian_batch(self):
        result = StreetModel(4, cars=[Arrival(18), Arrival(19)],
                             pedestrians=[Arrival(1), Arrival(20), Arrival(21)],
                             cars_at_stop=True, pedestrians_at_crossing=True).run()
        self.assertEqual([(p.start, p.end) for p in cars(result)], [(18, 20), (30, 32)])
        self.assertEqual([p.start for p in pedestrians(result)], [20, 50, 50])
        self.assert_traffic_rules(result)

    def test_exercise5_table_and_external_queue(self):
        result = exercise05.demo()
        self.assertEqual([p.entered_a for p in cars(result)], [0] * 5 + [12, 14, 16])
        self.assertEqual([(p.start, p.end) for p in cars(result)], [
            (10, 12), (12, 14), (14, 16), (16, 18), (18, 20),
            (30, 32), (32, 34), (34, 36),
        ])
        self.assertEqual(max(r["external_queue"] for r in result.monitoring), 3)
        self.assertEqual(result.finished_at, 36)
        self.assertEqual(result.monitoring[-1]["a_occupied"], 0)
        self.assertEqual([p.start for p in pedestrians(result)], [20, 20])
        self.assert_traffic_rules(result)
        self.assert_complete(result)

    def test_exercise6_closed_exit_and_pedestrians(self):
        result = exercise06.demo()
        self.assertEqual([p.start for p in cars(result)], [0, 2, 4, 6, 8, 60, 62, 64])
        self.assertEqual([p.exited for p in cars(result)[:5]], [60] * 5)
        self.assertGreater(cars(result)[5].blocked_b, 0)
        self.assertEqual([p.start for p in pedestrians(result)], [20, 20])
        self.assertEqual(max(r["b_straight_used"] for r in result.monitoring), 5)
        self.assertEqual(result.monitoring[-1]["b_straight_used"], 0)
        self.assert_traffic_rules(result)
        self.assert_complete(result)

    def test_exercise6_paired_arrivals(self):
        opened, blocked = exercise06.compare(seed=7)
        self.assertEqual([(p.id, p.appeared) for p in opened.records],
                         [(p.id, p.appeared) for p in blocked.records])
        self.assertGreaterEqual(sum(p.start - p.queued for p in cars(blocked)),
                                sum(p.start - p.queued for p in cars(opened)))
        self.assert_traffic_rules(opened)
        self.assert_traffic_rules(blocked)

    def test_slot_freed_after_green_is_rechecked(self):
        # Пять резервов заполнены; первый выход открывается в пешеходный интервал.
        model = StreetModel(6, cars=[Arrival(0)] * 6, pedestrians=[Arrival(1)],
                            cars_at_stop=True, pedestrians_at_crossing=True,
                            blocked_until=21)
        result = model.run()
        self.assertEqual(cars(result)[5].start, 30)
        self.assertEqual(pedestrians(result)[0].start, 20)
        self.assertEqual(model.free_b["straight"].level, 5)
        self.assertEqual(model.free_b["straight"].get_queue, [])
        self.assert_traffic_rules(result)

    def test_slot_freed_exactly_at_phase_boundary(self):
        model = StreetModel(6, cars=[Arrival(0)] * 6, pedestrians=[Arrival(1)],
                            cars_at_stop=True, pedestrians_at_crossing=True,
                            blocked_until=20)
        result = model.run()
        self.assertEqual(cars(result)[5].start, 30)
        self.assertEqual(model.free_b["straight"].level, 5)
        self.assertEqual(model.free_b["straight"].get_queue, [])
        self.assert_traffic_rules(result)

    def test_exercise7_synchronized_table(self):
        result = exercise07.demo()
        self.assertEqual([(p.start, p.end, p.arrived_b, p.start_b, p.exited)
                          for p in cars(result)], [
            (0, 2, 12, 12, 14), (24, 26, 36, 36, 38), (36, 38, 48, 48, 50),
        ])
        self.assert_traffic_rules(result)
        self.assert_complete(result)

    def test_exercise7_prefilled_left_isolated(self):
        result = exercise07.demo(prefilled=True)
        self.assertEqual(cars(result, "straight")[0].start, 0)
        self.assertEqual(cars(result, "right")[0].start, 36)
        self.assertEqual(cars(result, "left")[0].start, 204)
        initial = [p for p in result.records if p.initial]
        self.assertEqual([p.start_b for p in initial], [156, 158, 160])
        self.assertEqual([p.exited for p in initial], [158, 160, 162])
        self.assertEqual(result.summary()["car"]["initial"], 3)
        self.assertEqual(result.summary()["car"]["completed"], 6)
        self.assert_traffic_rules(result)
        self.assert_complete(result)

    def test_all_random_models_invariants_and_resources(self):
        for exercise in range(4, 8):
            for seed in (0, 7, 42):
                with self.subTest(exercise=exercise, seed=seed):
                    model = StreetModel(exercise, seed=seed)
                    result = model.run()
                    self.assert_complete(result)
                    self.assert_traffic_rules(result)
                    for route, free in model.free_b.items():
                        self.assertEqual(free.level, model.capacities[route])
                        self.assertEqual(free.get_queue, [])
                        self.assertEqual(model.holders[route], {})
                    if model.free_a is not None:
                        self.assertEqual(model.free_a.level, 5)
                    self.assertEqual(model.a_used, 0)
                    self.assertEqual(model.external_waiting, 0)

    def test_route_frequencies_and_independent_streams(self):
        result = StreetModel(7, seed=42, horizon=36000, pedestrians=[]).run()
        participants = cars(result)
        self.assertGreater(len(participants), 3000)
        for route, probability in (("straight", 0.5), ("left", 0.3), ("right", 0.2)):
            actual = sum(p.route == route for p in participants) / len(participants)
            self.assertAlmostEqual(actual, probability, delta=0.04)
        normal = StreetModel(7, seed=7, horizon=600).run()
        without_peds = StreetModel(7, seed=7, horizon=600, pedestrians=[]).run()
        self.assertEqual([(p.appeared, p.route) for p in cars(normal)],
                         [(p.appeared, p.route) for p in cars(without_peds)])

    def test_no_participants_finishes_with_controller(self):
        result = StreetModel(7, cars=[], pedestrians=[]).run()
        self.assertEqual(result.finished_at, 0)
        self.assertEqual(result.records, [])


if __name__ == "__main__":
    unittest.main()
