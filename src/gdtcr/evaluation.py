"""Strict completion-v2 sequence decoding and fixed-draw ranking summaries."""

from __future__ import annotations

from .model import BOS, CHAIN_TO_ID, EOS, ID_TO_AA, PAD


def decode_sample_v2(token_ids, target_chain):
    ids = [int(value) for value in token_ids]
    if len(ids) < 3 or ids[0] != BOS or ids[1] != CHAIN_TO_ID[target_chain]:
        return {"sequence": None, "valid": False, "reason": "invalid_prefix", "tokens": ids}
    residues = []
    eos_index = None
    reason = "missing_eos"
    for index, token in enumerate(ids[2:], 2):
        if token == EOS:
            eos_index = index
            reason = None
            break
        if token == PAD:
            reason = "pad_before_eos"
            break
        if token not in ID_TO_AA:
            reason = "invalid_residue_token"
            break
        residues.append(ID_TO_AA[token])
    if eos_index is not None and any(token != PAD for token in ids[eos_index + 1:]):
        reason = "tokens_after_eos"
    if reason is None and len(residues) < 6:
        reason = "too_short"
    if reason is None and len(residues) > 35:
        reason = "too_long"
    trimmed = list(ids)
    while len(trimmed) > 2 and trimmed[-1] == PAD:
        trimmed.pop()
    return {"sequence": "".join(residues) if reason is None else None,
            "valid": reason is None, "reason": reason,
            "observed_eos": eos_index is not None, "tokens": trimmed}


def ranked_generation_metrics(positives, ordered):
    positive_set = set(positives)
    ranks = [index + 1 for index, candidate in enumerate(ordered) if candidate in positive_set]
    best = min(ranks, default=None)
    return {"coverage": float(bool(ranks)), "mrr": 1 / best if best else 0.0,
            "mean_positive_rank": (sum(ranks) + (len(positive_set) - len(ranks)) *
                                   (len(ordered) + 1)) / max(len(positive_set), 1),
            **{f"hit_at_{k}": float(best is not None and best <= k) for k in (1, 5, 10)},
            **{f"recall_at_{k}": len([rank for rank in ranks if rank <= k]) / max(len(positive_set), 1)
               for k in (1, 5, 10)}}
