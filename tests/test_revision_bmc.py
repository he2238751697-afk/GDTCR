import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_revision_bmc import giant_edge_split, query_roles, selection_information
from evaluate_transfer_bmc import partner_similarity, training_index, transfer


class RevisionChecks(unittest.TestCase):
    def test_query_roles_avoid_single_hub_selection(self):
        pairs = [("hub", str(i)) for i in range(581)] + [(f"q{i}", f"p{i}") for i in range(62)]
        roles = query_roles(pairs)
        self.assertEqual(sorted(len({g for g,d in r}) for r in roles.values()), [16,16,31])
        self.assertEqual(set().union(*(set(r) for r in roles.values())), set(pairs))
        query_sets = [{g for g,d in r} for r in roles.values()]
        for i, a in enumerate(query_sets):
            for b in query_sets[i+1:]:
                self.assertFalse(a & b)

    def test_giant_edges_remain_unseen_with_seen_nodes(self):
        pairs = [(g,d) for g in ("A","B","C","D") for d in ("W","X","Y","Z")]
        parts = giant_edge_split(pairs, held_per_role=3)
        self.assertEqual(set().union(*(set(v) for v in parts.values())), set(pairs))
        self.assertEqual(sum(map(len, parts.values())), len(pairs))
        for col in (0,1):
            self.assertLessEqual({p[col] for p in parts['test']+parts['validation']},
                                 {p[col] for p in parts['train']})
        with self.assertRaises(ValueError):
            giant_edge_split([('A','W'),('A','X')], held_per_role=1)

    def test_transfer_does_not_inject_truth_and_has_lexical_ties(self):
        partners, frequency = training_index([('AAC','PPP'),('AAT','QQQ'),('AAC','QQQ')],0)
        candidates, neighbors = transfer('AAA',partners,frequency)
        self.assertEqual(neighbors,['AAC'])
        self.assertEqual(candidates,['QQQ','PPP'])
        self.assertNotIn('RRR',candidates)
        self.assertEqual(partner_similarity(['PPP','PPQ'], {'PPP'}), [0,1/-3])

    def test_selection_distractors_exclude_other_recorded_positives(self):
        info = selection_information([('A','X'),('B','Y')], [('A','X'),('A','Y'),('B','Y')],0)
        self.assertEqual(info['queries_without_distractors'],1)


if __name__ == '__main__':
    unittest.main()
