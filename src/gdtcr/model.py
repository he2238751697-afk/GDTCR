"""Compact shared encoder-decoder and an independently trainable pair ranker."""

from __future__ import annotations

import math

import torch
from torch import nn
from torch.nn import functional as F


AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"
PAD, BOS, EOS, MASK, GAMMA, DELTA = range(6)
AA_TO_ID = {aa: index + 6 for index, aa in enumerate(AMINO_ACIDS)}
ID_TO_AA = {value: key for key, value in AA_TO_ID.items()}
VOCAB_SIZE = len(AA_TO_ID) + 6
CHAIN_TO_ID = {"gamma": GAMMA, "delta": DELTA}


def encode_sequence(sequence: str) -> list[int]:
    try:
        return [AA_TO_ID[aa] for aa in sequence]
    except KeyError as error:
        raise ValueError(f"Unsupported amino acid: {error.args[0]}") from error


def make_batch(rows, device, corrupt=False, seed=None, mask_probability=None,
               conditional_rows=None):
    """Build model inputs; denoising corruption never changes decoder targets."""
    generator = None
    if seed is not None:
        generator = torch.Generator(device="cpu").manual_seed(seed)
    source_rows, decoder_rows, labels, damaged_rows, copy_rows = [], [], [], [], []
    if conditional_rows is not None and len(conditional_rows) != len(rows):
        raise ValueError("conditional_rows must match the number of source rows")
    for row_index, (chain, sequence) in enumerate(rows):
        source_tokens = encode_sequence(sequence)
        source_chain_id = CHAIN_TO_ID[chain]
        if conditional_rows is None:
            target_chain, target_sequence = chain, sequence
        else:
            target_chain, target_sequence = conditional_rows[row_index]
        target_chain_id = CHAIN_TO_ID[target_chain]
        target = encode_sequence(target_sequence)
        source_sequence = list(source_tokens)
        damaged = [False] * len(target)
        aligned_copy = list(source_tokens) if conditional_rows is None else []
        if corrupt and target:
            probability = mask_probability
            if probability is None:
                probability = 0.15 if torch.rand((), generator=generator).item() < 0.5 else 0.30
            n_mask = max(1, round(len(target) * probability))
            positions = torch.randperm(len(target), generator=generator)[:n_mask].tolist()
            for position in positions:
                damaged[position] = True
                choice = torch.rand((), generator=generator).item()
                if choice < 0.80:
                    source_sequence[position] = MASK
                elif choice < 0.90:
                    source_sequence[position] = 6 + int(torch.randint(
                        len(AMINO_ACIDS), (), generator=generator).item())
            delete_positions = set()
            desired_deletions = max(0, round(len(target) * 0.08))
            while len(delete_positions) < desired_deletions:
                start = int(torch.randint(len(target), (), generator=generator).item())
                span = 1 + int(torch.randint(3, (), generator=generator).item())
                delete_positions.update(range(start, min(len(target), start + span)))
                if len(delete_positions) >= len(target):
                    delete_positions.discard(start)
            for position in delete_positions:
                damaged[position] = True
            aligned_copy = [MASK if index in delete_positions else token
                            for index, token in enumerate(source_sequence)]
            source_sequence = [token for index, token in enumerate(source_sequence)
                               if index not in delete_positions]
        source_rows.append([source_chain_id] + source_sequence)
        decoder_rows.append([BOS, target_chain_id] + target)
        # The chain token predicts residue 1; each residue predicts its successor.
        labels.append([-100] + target + [EOS])
        damaged_rows.append(damaged)
        copy_rows.append(aligned_copy)

    max_source = max(map(len, source_rows))
    max_decoder = max(map(len, decoder_rows))
    source = torch.full((len(rows), max_source), PAD, dtype=torch.long)
    decoder = torch.full((len(rows), max_decoder), PAD, dtype=torch.long)
    target_labels = torch.full((len(rows), max_decoder), -100, dtype=torch.long)
    damaged_mask = torch.zeros((len(rows), max_decoder), dtype=torch.bool)
    copy_ids = torch.full((len(rows), max_decoder), MASK, dtype=torch.long)
    for index, (src, dec, label, damaged) in enumerate(
            zip(source_rows, decoder_rows, labels, damaged_rows)):
        source[index, :len(src)] = torch.tensor(src)
        decoder[index, :len(dec)] = torch.tensor(dec)
        target_labels[index, :len(label)] = torch.tensor(label)
        for residue_index, is_damaged in enumerate(damaged):
            damaged_mask[index, residue_index + 1] = is_damaged
        if copy_rows[index]:
            copy_ids[index, 1:len(copy_rows[index]) + 1] = torch.tensor(copy_rows[index])
    return {
        "source": source.to(device),
        "decoder": decoder.to(device),
        "labels": target_labels.to(device),
        "damaged_mask": damaged_mask.to(device),
        "aligned_copy_ids": copy_ids.to(device),
    }


class ConditionalSeq2Seq(nn.Module):
    def __init__(self, d_model=256, nhead=8, encoder_layers=4, decoder_layers=4,
                 dim_feedforward=1024, dropout=0.1, max_length=64):
        super().__init__()
        self.d_model = d_model
        self.max_length = max_length
        self.token_embedding = nn.Embedding(VOCAB_SIZE, d_model, padding_idx=PAD)
        self.position_embedding = nn.Embedding(max_length, d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model, nhead, dim_feedforward, dropout, batch_first=True,
            norm_first=True, activation="gelu")
        decoder_layer = nn.TransformerDecoderLayer(
            d_model, nhead, dim_feedforward, dropout, batch_first=True,
            norm_first=True, activation="gelu")
        self.encoder_norm = nn.LayerNorm(d_model)
        self.decoder_norm = nn.LayerNorm(d_model)
        self.encoder = nn.TransformerEncoder(encoder_layer, encoder_layers,
                                             norm=self.encoder_norm)
        self.decoder = nn.TransformerDecoder(decoder_layer, decoder_layers,
                                             norm=self.decoder_norm)
        self.output_bias = nn.Parameter(torch.zeros(VOCAB_SIZE))
        self.reset_parameters()

    def reset_parameters(self):
        nn.init.normal_(self.token_embedding.weight, mean=0.0, std=0.02)
        nn.init.normal_(self.position_embedding.weight, mean=0.0, std=0.02)
        with torch.no_grad():
            self.token_embedding.weight[PAD].zero_()

    def _embed(self, ids):
        if ids.shape[1] > self.max_length:
            raise ValueError(f"Sequence length {ids.shape[1]} exceeds {self.max_length}")
        positions = torch.arange(ids.shape[1], device=ids.device).unsqueeze(0)
        return self.token_embedding(ids) * math.sqrt(self.d_model) + self.position_embedding(positions)

    def encode(self, source):
        padding_mask = source.eq(PAD)
        encoded = self.encoder(self._embed(source), src_key_padding_mask=padding_mask)
        return encoded, padding_mask

    def forward(self, source, decoder):
        memory, source_padding = self.encode(source)
        target_padding = decoder.eq(PAD)
        length = decoder.shape[1]
        causal_mask = torch.triu(torch.ones(length, length, device=decoder.device,
                                            dtype=torch.bool), diagonal=1)
        decoded = self.decoder(
            self._embed(decoder), memory, tgt_mask=causal_mask,
            tgt_key_padding_mask=target_padding,
            memory_key_padding_mask=source_padding)
        return F.linear(decoded, self.token_embedding.weight, self.output_bias)

    @torch.no_grad()
    def sample(self, source, target_chain, max_new_tokens=None, temperature=1.0,
               top_p=1.0, num_samples=1, generator=None):
        """Autoregressively sample target sequences for a batch of source rows.

        The source batch is encoded once and repeated for ``num_samples``. The
        returned tensor contains ``BOS``, the target chain token, generated
        residues, and ``EOS``/``PAD`` after termination. This method is kept
        separate from teacher-forced ``forward`` so training behavior is
        unchanged.
        """
        if temperature <= 0:
            raise ValueError("temperature must be positive")
        if not 0 < top_p <= 1:
            raise ValueError("top_p must be in (0, 1]")
        if num_samples < 1:
            raise ValueError("num_samples must be positive")
        if isinstance(target_chain, str):
            target_chain = CHAIN_TO_ID[target_chain]
        if source.ndim != 2:
            raise ValueError("source must have shape [batch, length]")
        max_new_tokens = max_new_tokens or (self.max_length - 2)
        if max_new_tokens < 1 or max_new_tokens + 2 > self.max_length:
            raise ValueError("max_new_tokens does not fit max_length")

        memory, source_padding = self.encode(source)
        batch_size = source.shape[0]
        memory = memory.repeat_interleave(num_samples, dim=0)
        source_padding = source_padding.repeat_interleave(num_samples, dim=0)
        decoder = torch.full((batch_size * num_samples, 2), PAD,
                             dtype=torch.long, device=source.device)
        decoder[:, 0] = BOS
        decoder[:, 1] = target_chain
        finished = torch.zeros(decoder.shape[0], dtype=torch.bool, device=source.device)
        eos_tail = torch.full((decoder.shape[0], 1), PAD, dtype=torch.long,
                              device=source.device)
        for _ in range(max_new_tokens):
            target_padding = decoder.eq(PAD)
            length = decoder.shape[1]
            causal_mask = torch.triu(torch.ones(length, length, device=decoder.device,
                                                dtype=torch.bool), diagonal=1)
            decoded = self.decoder(
                self._embed(decoder), memory, tgt_mask=causal_mask,
                tgt_key_padding_mask=target_padding,
                memory_key_padding_mask=source_padding)
            logits = F.linear(decoded[:, -1], self.token_embedding.weight,
                              self.output_bias)
            logits[:, PAD] = -torch.inf
            logits[:, BOS] = -torch.inf
            logits[:, MASK] = -torch.inf
            logits[:, GAMMA] = -torch.inf
            logits[:, DELTA] = -torch.inf
            logits = logits / temperature
            if top_p < 1.0:
                sorted_logits, sorted_indices = torch.sort(logits, descending=True, dim=-1)
                probabilities = sorted_logits.softmax(dim=-1)
                cumulative = probabilities.cumsum(dim=-1)
                remove = cumulative - probabilities >= top_p
                sorted_logits[remove] = -torch.inf
                logits = torch.full_like(logits, -torch.inf)
                logits.scatter_(1, sorted_indices, sorted_logits)
            next_token = torch.multinomial(logits.softmax(dim=-1), 1,
                                           generator=generator).squeeze(1)
            next_token = torch.where(finished, torch.full_like(next_token, PAD), next_token)
            decoder = torch.cat((decoder, next_token[:, None]), dim=1)
            finished = finished | next_token.eq(EOS)
            if bool(finished.all()):
                break
        if decoder.shape[1] < self.max_length:
            decoder = torch.cat((decoder, eos_tail.repeat(1, self.max_length - decoder.shape[1])), dim=1)
        return decoder[:, :self.max_length]

class PairRanker(nn.Module):
    """Independent pair score using a shared pretrained sequence encoder."""
    def __init__(self, encoder: ConditionalSeq2Seq, projection_dim=128, hidden_dim=256,
                 dropout=0.15, version=1):
        super().__init__()
        self.encoder = encoder
        if version not in (1, 2):
            raise ValueError("Unsupported ranker version")
        self.version = version
        self.config = {"projection_dim": projection_dim, "hidden_dim": hidden_dim,
                       "dropout": dropout, "version": version}
        def projection():
            return nn.Sequential(nn.Linear(encoder.d_model, projection_dim), nn.GELU(), nn.LayerNorm(projection_dim))
        if version == 1:
            self.projection = projection()
        else:
            self.gamma_projection = projection()
            self.delta_projection = projection()
        self.interaction = nn.Sequential(
            nn.Linear(4 * projection_dim, hidden_dim), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1))

    def encode_sequences(self, chain, sequences):
        rows = [(chain, sequence) for sequence in sequences]
        batch = make_batch(rows, next(self.parameters()).device)
        encoded, padding = self.encoder.encode(batch["source"])
        valid = ((~padding) if self.version == 1 else batch["source"].ge(6)).unsqueeze(-1).to(encoded.dtype)
        pooled = (encoded * valid).sum(1) / valid.sum(1).clamp_min(1.0)
        projection = self.projection if self.version == 1 else getattr(self, chain + "_projection")
        return F.normalize(projection(pooled), dim=-1)

    def score_matrix(self, gamma_vectors, delta_vectors):
        """Return scores with gamma on rows and delta on columns.

        The interaction head is asymmetric: concatenation order is part of
        the trained model and must not change with the retrieval direction.
        """
        gamma = gamma_vectors[:, None, :].expand(-1, delta_vectors.shape[0], -1)
        delta = delta_vectors[None, :, :].expand(gamma_vectors.shape[0], -1, -1)
        features = torch.cat((gamma, delta, gamma * delta, (gamma - delta).abs()), dim=-1)
        scores = self.interaction(features).squeeze(-1)
        return scores if self.version == 1 else scores + (gamma * delta).sum(-1)

    def score_pairs(self, gamma_vectors, delta_vectors):
        if gamma_vectors.shape != delta_vectors.shape:
            raise ValueError("Aligned pair vectors must have identical shapes")
        features = torch.cat((gamma_vectors, delta_vectors, gamma_vectors * delta_vectors,
                              (gamma_vectors - delta_vectors).abs()), dim=-1)
        scores = self.interaction(features).squeeze(-1)
        return scores if self.version == 1 else scores + (gamma_vectors * delta_vectors).sum(-1)

    def score_queries(self, source_chain, source_vectors, candidate_vectors):
        """Return query-by-candidate scores in the canonical gamma/delta order."""
        if source_chain == "gamma":
            return self.score_matrix(source_vectors, candidate_vectors)
        if source_chain == "delta":
            return self.score_matrix(candidate_vectors, source_vectors).transpose(0, 1)
        raise ValueError(f"Unsupported source chain: {source_chain}")


def multi_positive_loss(scores, positive_mask):
    """Multi-positive InfoNCE; known alternative partners are never negatives."""
    if not positive_mask.any(dim=1).all():
        raise ValueError("Every query must have at least one positive candidate")
    row_loss = torch.logsumexp(scores, dim=1) - torch.logsumexp(
        scores.masked_fill(~positive_mask, -torch.inf), dim=1)
    if not positive_mask.any(dim=0).all():
        raise ValueError("Every candidate must be positive for at least one query")
    column_loss = torch.logsumexp(scores, dim=0) - torch.logsumexp(
        scores.masked_fill(~positive_mask, -torch.inf), dim=0)
    return (row_loss.mean() + column_loss.mean()) / 2
