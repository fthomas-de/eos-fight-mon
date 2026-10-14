import unittest

from snap import snap_offset

SCREEN = [(0, 0, 1920, 1040)]


class SnapTest(unittest.TestCase):
    def test_docks_to_right_edge_and_aligns_top(self):
        # window 10 px right of a neighbour's right edge, 6 px lower: moves left and up
        self.assertEqual(snap_offset((510, 106, 800, 300), [(100, 100, 500, 400)], SCREEN), (-10, -6))

    def test_docks_below(self):
        self.assertEqual(snap_offset((100, 408, 300, 500), [(100, 100, 500, 400)], SCREEN), (0, -8))

    def test_far_away_stays(self):
        self.assertEqual(snap_offset((700, 600, 900, 700), [(100, 100, 500, 400)], SCREEN), (0, 0))

    def test_not_beside_each_other_no_side_dock(self):
        # right of the neighbour but far below it: no horizontal docking
        self.assertEqual(snap_offset((505, 600, 800, 700), [(100, 100, 500, 400)], SCREEN), (0, 0))

    def test_screen_edge(self):
        self.assertEqual(snap_offset((1700, 1030, 1910, 1035), [], SCREEN), (10, 5))


if __name__ == "__main__":
    unittest.main()
