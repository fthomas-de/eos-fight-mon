import tempfile
import unittest

import pathlib
from fight import DRONES, IDLE_END, Fight, history_secs, list_history, load_history, save_history, to_event
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
        self.assertCountEqual(t["flows"], [["dmg", "A", "Foe", 20], ["dmg", "Foe", "A", 30],  # drones: owner
                                           ["jam", DRONES, "B", 1], ["point", "Rat", "B", 1]])
        self.assertEqual(t["left"], ["A", "B"])
        self.assertEqual(t["ships"], {"Foe": "Sentinel"})  # last ship seen wins
        self.assertNotIn("hidden", t)

    def test_friendly_fire_is_dropped(self):
        self.f.add([ev("dmg", "A", "B", 50, "A"), ev("shield", "Mate", "B", 100, "B"),
                    ev("dmg", "A", "Mate", 30, "A"), ev("dmg", "Foe", "A", 20, "A")])
        self.assertCountEqual(self.f.tick(0)["flows"], [["shield", "Mate", "B", 100], ["dmg", "Foe", "A", 20]])

    def test_friendly_fire_on_request(self):
        self.f.friendly_fire = True
        self.f.add([ev("dmg", "A", "B", 50, "A"), ev("dmg", "A", "B", 50, "B"), ev("shield", "Mate", "B", 100, "B"),
                    ev("dmg", "A", "Mate", 30, "A")])
        self.assertCountEqual(self.f.tick(0)["flows"], [["dmg", "A", "B", 50], ["shield", "Mate", "B", 100],
                                                        ["dmg", "A", "Mate", 30]])  # still logged once, not twice

    def test_solo_shows_own_ship_and_enemies_only(self):
        f = Fight(solo=True)
        f.listeners = {"A"}
        f.add([ev("dmg", "Foe", "A", 30, "A"), ev("shield", "Mate", "A", 100, "A"),
               ev("point", "Rat", "Mate", 1, "A"), ev("cap", "A", "Turncoat", 50, "A"),
               ev("neut", "Turncoat", "A", 10, "A")])
        t = f.tick(0)
        self.assertNotIn(["point", "Rat", "Mate", 1], t["flows"])  # does not involve the own ship
        self.assertNotIn(["neut", "Turncoat", "A", 10], t["flows"])  # friendly fire
        self.assertEqual(t["hidden"], ["Mate", "Turncoat"])  # reps with us: friends
        f.end()
        self.assertEqual(list(pathlib.Path(self.tmp.name).iterdir()), [])  # never stored

    def test_idle_end_and_history(self):
        self.assertIsNone(self.f.tick(0))  # no fight yet
        self.f.add([ev("dmg", "Foe", "A", 50, "A")])
        self.f.tick(100)
        self.assertEqual(self.f.tick(102)["start"], 100)  # empty ticks keep coming while the fight runs
        self.assertFalse(self.f.ended(100 + IDLE_END - 1))
        self.assertTrue(self.f.ended(100 + IDLE_END))
        self.f.end()
        self.assertIsNone(self.f.tick(200))
        [name] = list_history(self.tmp.name)
        ticks = load_history(self.tmp.name, name)
        self.assertEqual([t["flows"] for t in ticks], [[["dmg", "Foe", "A", 50]]])  # idle tail dropped
        self.assertEqual(load_history(self.tmp.name, "../" + name), [])
        save_history(self.tmp.name, "20991231_235959.jsonl.gz", ticks)
        open(f"{self.tmp.name}/evil.jsonl.gz", "w").close()
        self.assertEqual(list_history(self.tmp.name), ["20991231_235959.jsonl.gz", name])  # newest first
        self.assertEqual(history_secs(self.tmp.name, [name, "missing.jsonl.gz"]), {name: 2})  # one tick, no idle tail

    def test_to_event(self):
        good = ["dmg", "A", None, "B", "Gila", 10, None, "A"]
        self.assertEqual(to_event(good), Event(*good))
        for bad in (["evil", *good[1:]], [*good[:5], -1, *good[6:]], [*good[:5], "10", *good[6:]],
                    [*good[:1], "x" * 101, *good[2:]], good[:7], 5, None):
            self.assertIsNone(to_event(bad), bad)


if __name__ == "__main__":
    unittest.main()
