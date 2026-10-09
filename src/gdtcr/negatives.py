"""Training-only constructed negatives; no held-out pair labels are consulted."""

import random
from collections import Counter, defaultdict


def terminal_distance(left, right):
    return sum(a != b for a, b in zip(left[:3] + left[-3:], right[:3] + right[-3:]))


class TrainingNegativeSampler:
    def __init__(self, pairs, mode="mixed"):
        if mode not in ("random", "mixed"):
            raise ValueError("Explicit negative mode must be random or mixed")
        self.mode = mode
        self.known = set(pairs)
        self.pools = {"gamma": sorted({g for g, _ in pairs}), "delta": sorted({d for _, d in pairs})}
        self.positive = {"gamma": defaultdict(set), "delta": defaultdict(set)}
        self.by_length = {"gamma": defaultdict(list), "delta": defaultdict(list)}
        for g, d in pairs:
            self.positive["gamma"][g].add(d)
            self.positive["delta"][d].add(g)
        for chain, pool in self.pools.items():
            for sequence in pool:
                self.by_length[chain][len(sequence)].append(sequence)
        self.hard_cache = {}
        self.stats = Counter()

    def sample(self, positives, ratio, seed):
        rng = random.Random(seed)
        negatives = []
        for gamma, delta in positives:
            for _ in range(ratio):
                source_chain = rng.choice(("gamma", "delta"))
                target_chain = "delta" if source_chain == "gamma" else "gamma"
                source, reference = (gamma, delta) if source_chain == "gamma" else (delta, gamma)
                exclude = self.positive[source_chain][source]
                if len(exclude) >= len(self.pools[target_chain]):
                    self.stats["no_unrecorded_target"] += 1
                    continue
                use_hard = self.mode == "mixed" and rng.random() < .5
                candidate = None
                if use_hard:
                    key = (target_chain, reference)
                    if key not in self.hard_cache:
                        pool = [t for length in (len(reference) - 1, len(reference), len(reference) + 1)
                                for t in self.by_length[target_chain].get(length, ())]
                        self.hard_cache[key] = sorted(pool, key=lambda t: (
                            abs(len(t) - len(reference)), terminal_distance(t, reference), t))
                    eligible = [t for t in self.hard_cache[key] if t not in exclude][:64]
                    if eligible:
                        candidate = rng.choice(eligible)
                        self.stats["hard_draws"] += 1
                    else:
                        self.stats["hard_fallbacks"] += 1
                if candidate is None:
                    pool = self.pools[target_chain]
                    candidate = rng.choice(pool)
                    while candidate in exclude:
                        candidate = rng.choice(pool)
                    self.stats["random_draws"] += 1
                pair = (source, candidate) if source_chain == "gamma" else (candidate, source)
                assert pair not in self.known
                negatives.append(pair)
                self.stats["length_difference_" + str(abs(len(candidate) - len(reference)))] += 1
                self.stats["source_" + source_chain] += 1
        return negatives
