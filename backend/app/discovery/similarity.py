"""
Discovery — Sequence Similarity
==================================
Provides deterministic, explainable sequence similarity calculations.

TWO similarity metrics are used:

1. EXACT MATCH (primary)
   Two sequences are considered identical if their fingerprints match.
   similarity = 1.0

2. JACCARD SIMILARITY (fallback for fuzzy grouping)
   Measures token-set overlap between two sequences.

   jaccard(A, B) = |A ∩ B| / |A ∪ B|

   where A and B are sets of "application/action" tokens.

   Example:
       A = {"Gmail/open_email", "Gmail/download", "CRM/find_customer",
            "CRM/update_customer", "Slack/send_message"}
       B = {"Gmail/open_email", "Gmail/download", "CRM/find_customer",
            "CRM/update_customer", "Slack/send_message"}
       jaccard(A, B) = 5/5 = 1.0 (exact match)

   Why Jaccard?
       - It is order-independent (good for detecting partial overlaps)
       - It is transparent and reproducible
       - It does not require training data
       - It degrades gracefully for partially matching sequences

   Note:
       For workflow discovery, exact-match fingerprinting (used in
       repetition_detector.py) is the primary grouping mechanism.
       Jaccard is used to calculate the *reported* similarity score
       and to support future fuzzy cluster merging.

3. AVERAGE PAIRWISE SIMILARITY
   When a candidate has N sessions, the reported similarity is the
   mean of all N*(N-1)/2 pairwise Jaccard values.

   For N=3 sessions with identical sequences: average = 1.0
   For mixed sessions: average reflects the actual overlap.
"""

from __future__ import annotations

from typing import List, Tuple

from app.discovery.normalizer import NormalisedSequence


def jaccard_similarity(a: NormalisedSequence, b: NormalisedSequence) -> float:
    """
    Jaccard similarity between two normalised sequences.

    Returns:
        float in [0.0, 1.0]
        1.0 = identical token sets
        0.0 = completely disjoint token sets
    """
    if not a.token_set and not b.token_set:
        return 1.0  # Two empty sequences are trivially identical
    if not a.token_set or not b.token_set:
        return 0.0

    intersection = len(a.token_set & b.token_set)
    union = len(a.token_set | b.token_set)
    return intersection / union if union > 0 else 0.0


def average_pairwise_similarity(sequences: List[NormalisedSequence]) -> float:
    """
    Calculate the mean pairwise Jaccard similarity across all sequence pairs.

    For a group of N sequences:
        Pairs: N*(N-1)/2
        If N < 2: return 1.0 (single sequence is perfectly self-similar)

    Returns:
        float in [0.0, 1.0]
    """
    if len(sequences) < 2:
        return 1.0

    total = 0.0
    count = 0
    for i in range(len(sequences)):
        for j in range(i + 1, len(sequences)):
            total += jaccard_similarity(sequences[i], sequences[j])
            count += 1

    return total / count if count > 0 else 1.0


def pairwise_similarities(
    sequences: List[NormalisedSequence],
) -> List[Tuple[str, str, float]]:
    """
    Return all pairwise (session_id_a, session_id_b, similarity) tuples.

    Useful for debugging and transparency reporting.
    """
    pairs = []
    for i in range(len(sequences)):
        for j in range(i + 1, len(sequences)):
            sim = jaccard_similarity(sequences[i], sequences[j])
            pairs.append((sequences[i].session_id, sequences[j].session_id, sim))
    return pairs
