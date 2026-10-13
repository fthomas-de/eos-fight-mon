import tempfile
import unittest

from fight import DRONES_L, DRONES_R, IDLE_END, Fight, list_history, load_history, to_event
from logparse import Event


def ev(kind, src, dst, amount, logger, weapon=None, src_ship=None, dst_ship=None):
    return Event(kind, src, src_ship, dst, dst_ship, amount, weapon, logger)


class FightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Fight(self.tmp.name)
        self.f.listeners = {"A", "B"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_both_clients_log_one_rep_once(self):
        self.f.add([ev("shield", "A", "B", 100, "A"), ev("shield", "A", "B", 100, "B")])
        self.assertEqual(self.f.tick(0)["flows"], [["shield", "A", "B", 100]])

    def test_drones_and_sides(self):
        self.f.add([ev("dmg", "A", "Foe", 20, "A", "Republic Fleet Warrior", dst_ship="Orthrus"),
                    ev("dmg", "Foe", "A", 30, "A", "Imperial Navy Acolyte", src_ship="Sentinel"),
                    ev("jam", "Hornet EC-300", "B", 1, "B", "Hornet EC-300"),
                    ev("point", "Rat", "B", 1, "A"), ev("point", "Rat", "B", 1, "B")])
        t = self.f.tick(0)
        self.assertCountEqual(t["flows"], [["dmg", DRONES_L, "Foe", 20], ["dmg", DRONES_R, "A", 30],
                                           ["jam", DRONES_R, "B", 1], ["point", "Rat", "B", 1]])
        self.assertEqual(t["left"], ["A", "B"])
        self.assertEqual(t["ships"], {"Foe": "Orthrus"})

    def test_idle_end_and_history(self):
        self.assertIsNone(self.f.tick(0))  # no fight yet
        self.f.add([ev("dmg", "Foe", "A", 50, "A")])
        self.f.tick(100)
        self.assertIsNotNone(self.f.tick(102))  # empty ticks keep coming while the fight runs
        self.assertFalse(self.f.ended(100 + IDLE_END - 1))
        self.assertTrue(self.f.ended(100 + IDLE_END))
        self.f.end()
        self.assertIsNone(self.f.tick(200))
        [name] = list_history(self.tmp.name)
        ticks = load_history(self.tmp.name, name)
        self.assertEqual([t["flows"] for t in ticks], [[["dmg", "Foe", "A", 50]]])  # idle tail dropped
        self.assertEqual(load_history(self.tmp.name, "../" + name), [])

    def test_to_event(self):
        good = ["dmg", "A", None, "B", "Gila", 10, None, "A"]
        self.assertEqual(to_event(good), Event(*good))
        for bad in (["evil", *good[1:]], [*good[:5], -1, *good[6:]], [*good[:5], "10", *good[6:]],
                    [*good[:1], "x" * 101, *good[2:]], good[:7], 5, None):
            self.assertIsNone(to_event(bad), bad)


if __name__ == "__main__":
    unittest.main()
