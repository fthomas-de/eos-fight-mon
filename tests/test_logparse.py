import os
import tempfile
import time
import unittest
from pathlib import Path

from logparse import Event, LogWatcher, characters, parse

ME = "Me Myself"
P = "[ 2026.10.12 18:15:00 ] (combat) "
# real gamelog lines, names swapped
DMG_IN = P + ("<color=0xffcc0000><b>305</b> <color=0x77ffffff><font size=10>from</font> <b><color=0xffffffff>"
              "Foe One[ABC](Jackdaw)</b><font size=10><color=0x77ffffff> - Caldari Navy Nova Light Missile - Hits")
DMG_OUT = P + ("<color=0xff00ffff><b>23</b> <color=0x77ffffff><font size=10>to</font> <b><color=0xffffffff>"
               "Foe Two[ABC](Orthrus)</b><font size=10><color=0x77ffffff> - Republic Fleet Warrior - Penetrates")
DMG_NPC = P + ("<color=0xffcc0000><b>16</b> <color=0x77ffffff><font size=10>from</font> <b><color=0xffffffff>"
               "Siphoning Guardian</b><font size=10><color=0x77ffffff> - Smashes")
SHIELD_BY = P + ("<color=0xffccff66><b>75</b><color=0x77ffffff><font size=10> remote shield boosted by </font>"
                 "<b><color=0xffffffff>Friend One [XYZ]&lt;ALLY&gt; (Gila)'1'</b><color=0x77ffffff><font size=10>"
                 " - Small Murky Compact Remote Shield Booster</font>")
CAP_TO = P + ("<color=0xffccff66><b>122</b><color=0x77ffffff><font size=10> remote capacitor transmitted to </font>"
              "<b><color=0xffffffff>Friend One [XYZ]&lt;ALLY&gt; (Gila)'1'</b><color=0x77ffffff><font size=10>"
              " - Corpum C-Type Medium Remote Capacitor Transmitter</font>")
ARMOR_BY = P + ("<color=0xffccff66><b>493</b><color=0x77ffffff><font size=10> remote armor repaired by </font>"
                "<b><color=0xffffffff><font size=12><color=0xFF40FFFF><b>Guardian</b> </color></font></b>"
                "<color=0x77ffffff><font size=10> - Large Solace Scoped Remote Armor Repairer</font>")
NEUT_OUT = P + ("<color=0xff7fffff><b>10 GJ</b><color=0x77ffffff><font size=10> energy neutralized </font><b>"
                "<color=0xffffffff><font size=12><color=0xFF40FFFF><b>Vexor</b> </color></font></b>"
                "<color=0x77ffffff><font size=10> - Small Infectious Scoped Energy Neutralizer</font>")
NEUT_IN = NEUT_OUT.replace("0xff7fffff", "0xffe57f7f")
NOS_OUT = P + ("<color=0xff7fffff><b>+3 GJ</b><color=0x77ffffff><font size=10> energy drained from </font><b>"
               "<color=0xffffffff><font size=12><color=0xFF40FFFF><b>Vexor</b> </color></font></b>"
               "<color=0x77ffffff><font size=10> - Small Ghoul Compact Energy Nosferatu</font>")
NOS_IN = P + ("<color=0xffe57f7f><b>-1 GJ</b><color=0x77ffffff><font size=10> energy drained to </font><b>"
              "<color=0xffffffff><font size=12><color=0xFF40FFFF><b>Cruor</b> </color></font></b>"
              "<color=0x77ffffff><font size=10> - Small Ghoul Compact Energy Nosferatu</font>")
POINT_YOU = P + ("<color=0xffffffff><b>Warp disruption attempt</b> <color=0x77ffffff><font size=10>from</font> "
                 "<color=0xffffffff><b>Collapsing Forager</b> <color=0x77ffffff><font size=10>to <b>"
                 "<color=0xffffffff></font>you!")
SCRAM = P + ("<color=0xffffffff><b>Warp scramble attempt</b> <color=0x77ffffff><font size=10>from</font> "
             "<color=0xffffffff><b>Foe One [ABC]&lt;BAD&gt; (Myrmidon)'T3'</b> <color=0x77ffffff><font size=10>to "
             "<b><color=0xffffffff></font>Friend One [XYZ] (Flycatcher)'3.50'")
JAM = P + ("<color=0x77ffffff><font size=10>You're</font> <color=0xffffffff><b>jammed</b> <color=0x77ffffff>"
           "<font size=10>by</font> <color=0xffffffff><b><font size=12><color=0xFF40FFFF><b>Rook</b> </color>"
           "</font></b><color=0x77ffffff><font size=10> - Umbra Scoped Radar ECM</font>")
MISS = P + "Your Republic Fleet Warrior misses Foe Two completely - Republic Fleet Warrior"
NOTIFY = "[ 2026.10.12 18:15:00 ] (notify) Ship stopping"


class ParseTest(unittest.TestCase):
    def test_lines(self):
        cases = {
            DMG_IN: Event("dmg", "Foe One", "Jackdaw", ME, None, 305, "Caldari Navy Nova Light Missile", ME),
            DMG_OUT: Event("dmg", ME, None, "Foe Two", "Orthrus", 23, "Republic Fleet Warrior", ME),
            DMG_NPC: Event("dmg", "Siphoning Guardian", None, ME, None, 16, None, ME),
            SHIELD_BY: Event("shield", "Friend One", "Gila", ME, None, 75, "Small Murky Compact Remote Shield Booster", ME),
            CAP_TO: Event("cap", ME, None, "Friend One", "Gila", 122,
                          "Corpum C-Type Medium Remote Capacitor Transmitter", ME),
            ARMOR_BY: Event("armor", "Guardian", None, ME, None, 493, "Large Solace Scoped Remote Armor Repairer", ME),
            NEUT_OUT: Event("neut", ME, None, "Vexor", None, 10, "Small Infectious Scoped Energy Neutralizer", ME),
            NEUT_IN: Event("neut", "Vexor", None, ME, None, 10, "Small Infectious Scoped Energy Neutralizer", ME),
            NOS_OUT: Event("nos", ME, None, "Vexor", None, 3, "Small Ghoul Compact Energy Nosferatu", ME),
            NOS_IN: Event("nos", "Cruor", None, ME, None, 1, "Small Ghoul Compact Energy Nosferatu", ME),
            POINT_YOU: Event("point", "Collapsing Forager", None, ME, None, 1, None, ME),
            SCRAM: Event("scram", "Foe One", "Myrmidon", "Friend One", "Flycatcher", 1, None, ME),
            JAM: Event("jam", "Rook", None, ME, None, 1, "Umbra Scoped Radar ECM", ME),
            MISS: None,
            NOTIFY: None,
        }
        for line, want in cases.items():
            self.assertEqual(parse(line, ME), want, line)


HEADER = "------------------------------------------------------------\r\n  Gamelog\r\n  Listener: {}\r\n" \
         "  Session Started: 2026.10.12 18:00:00\r\n------------------------------------------------------------\r\n"


class WatcherTest(unittest.TestCase):
    def test_tail(self):
        with tempfile.TemporaryDirectory() as d:
            old = Path(d, "old.txt")
            old.write_text(HEADER.format(ME) + DMG_IN + "\r\n", newline="")
            w = LogWatcher()
            self.assertEqual(w.poll(d, ME), [])  # what was there before start is skipped

            with open(old, "a", newline="") as fh:
                fh.write(DMG_OUT + "\r\n" + DMG_IN[:40])  # second line still being written
            self.assertEqual([e.kind for e in w.poll(d, ME)], ["dmg"])
            with open(old, "a", newline="") as fh:
                fh.write(DMG_IN[40:] + "\r\n")
            self.assertEqual([e.src for e in w.poll(d, ME)], ["Foe One"])

            Path(d, "new.txt").write_text(HEADER.format("Alt") + JAM + "\r\n", newline="")
            self.assertEqual(w.poll(d, ME), [])  # another character's log is not ours
            os.utime(old, (time.time() - 60, time.time() - 60))
            self.assertEqual(characters(d), ["Alt", ME])

            self.assertEqual(w.poll(d, "Alt"), [])  # switching character skips its past as well
            with open(Path(d, "new.txt"), "a", newline="") as fh:
                fh.write(JAM + "\r\n")
            self.assertEqual([e.logger for e in w.poll(d, "Alt")], ["Alt"])

            stale = time.time() - 3 * 86400
            os.utime(old, (stale, stale))
            self.assertEqual(characters(d), ["Alt"])


if __name__ == "__main__":
    unittest.main()
