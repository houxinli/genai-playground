import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tasks.fitness.src.normalize import Normalizer
from tasks.fitness.src.parser import _clean_line, parse_log

ANCHOR = date(2026, 5, 21)


def sets_for(body: str, header: str = "5.19 push", normalizer=None):
    return parse_log(f"{header}\n{body}\n", today=ANCHOR, normalizer=normalizer).sets


class ModernNotationTest(unittest.TestCase):
    def test_weight_carries_forward_across_sets(self):
        s = sets_for("坐姿杠铃推举 60deg 上F下8 85lbs 12 rpe8 95lbs 6 rpe8 4 rpe9 7 rpe10")
        self.assertEqual(
            [(x.weight, x.reps, x.rpe) for x in s],
            [(85.0, 12, 8.0), (95.0, 6, 8.0), (95.0, 4, 9.0), (95.0, 7, 10.0)],
        )
        self.assertEqual(s[0].setup, "60deg 上F下8")

    def test_rpe_without_reps_repeats_previous_reps(self):
        s = sets_for("split squat 35lbs 8 rpe8 rpe8 rpe8")
        self.assertEqual([(x.weight, x.reps, x.rpe) for x in s],
                         [(35.0, 8, 8.0), (35.0, 8, 8.0), (35.0, 8, 8.0)])

    def test_reps_without_rpe_still_become_sets(self):
        s = sets_for("kettle bell half deadlift 25lbs 10 10 rpe6")
        self.assertEqual([(x.reps, x.rpe) for x in s], [(10, None), (10, 6.0)])

    def test_stuck_rep_rpe_tokens_split(self):
        s = sets_for("俯卧撑 0lbs 20 rpe8 20rpe8 30rpe9")
        self.assertEqual([(x.reps, x.rpe) for x in s], [(20, 8.0), (20, 8.0), (30, 9.0)])

    def test_parenthetical_note_is_lifted_out(self):
        s = sets_for("rdl 35lbs 8 rpe8（grip issue） 25lbs 10 rpe9")
        self.assertEqual(s[0].note, "grip issue")
        self.assertEqual((s[0].weight, s[0].reps), (35.0, 8))
        self.assertEqual((s[-1].weight, s[-1].reps), (25.0, 10))


class CompactNotationTest(unittest.TestCase):
    def test_weight_sets_reps_expands(self):
        s = sets_for("辅助引体 40 4 12", header="7.22 pull", normalizer=Normalizer())
        self.assertEqual(len(s), 4)
        self.assertTrue(all((x.weight, x.reps) == (40.0, 12) for x in s))
        self.assertEqual(s[0].exercise, "assisted_chin_up")
        self.assertEqual(s[0].weight_type, "assisted")

    def test_equal_triple_is_three_rep_sets_not_weight_sets_reps(self):
        s = sets_for("trx 45deg 12 12 12", header="5.18 pull")
        self.assertEqual(len(s), 3)
        self.assertTrue(all(x.reps == 12 and x.weight is None for x in s))

    def test_two_numbers_are_sets_and_reps(self):
        s = sets_for("push up 4 20")
        self.assertEqual(len(s), 4)
        self.assertTrue(all(x.reps == 20 for x in s))


class DatingTest(unittest.TestCase):
    def test_year_rolls_back_across_december_boundary(self):
        log = "1.2 push\nbench press 95lbs 5 rpe8\n# 12.30 pull\n坐姿划船 100 3 8\n"
        sets = parse_log(log, today=ANCHOR).sets
        jan = [x for x in sets if x.exercise_raw == "bench press"][0]
        dec = [x for x in sets if "坐姿划船" in x.exercise_raw][0]
        self.assertEqual(jan.date, date(2026, 1, 2))
        self.assertEqual(dec.date, date(2025, 12, 30))


class NormalizationAndCleaningTest(unittest.TestCase):
    def test_deadlift_is_not_mangled_by_ea_stripping(self):
        cleaned, _ = _clean_line("kettle bell half deadlift 25lbs")
        self.assertIn("deadlift", cleaned)

    def test_aliases_collapse_to_one_canonical(self):
        nz = Normalizer()
        self.assertEqual(nz("辅助引体")[0], "assisted_chin_up")
        self.assertEqual(nz("assisted chin up")[0], "assisted_chin_up")
        self.assertEqual(nz("Chin Assist")[0], "assisted_chin_up")

    def test_est_1rm_only_for_loaded(self):
        nz = Normalizer()
        loaded = sets_for("bench press 95lbs 10 rpe8", normalizer=nz)[0]
        self.assertAlmostEqual(loaded.est_1rm, round(95 * (1 + 10 / 30), 1))
        body = sets_for("push up 0lbs 20 rpe8", normalizer=nz)[0]
        self.assertIsNone(body.est_1rm)


if __name__ == "__main__":
    unittest.main()
