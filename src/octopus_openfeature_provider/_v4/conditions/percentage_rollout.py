"""Buckets a targeting key into a percentage rollout.

Hashing the flag's evaluation key together with the targeting key keeps a bucket
stable across evaluations, while giving each flag an independent spread of
targeting keys. Every provider library shares this bucketing, so a rollout lands
on the same users whichever one a product uses.
"""

_MASK_32 = 0xFFFFFFFF
_C1 = 0xCC9E2D51
_C2 = 0x1B873593


def includes(evaluation_key: str, targeting_key: str, percentage: int) -> bool:
    """Whether ``targeting_key`` falls within the first ``percentage`` percent of
    targeting keys for the flag identified by ``evaluation_key``."""
    return get_normalized_number(evaluation_key, targeting_key) <= percentage


def get_normalized_number(evaluation_key: str, targeting_key: str) -> int:
    """A deterministic bucket from 1 to 100 inclusive for the two keys.

    Separate from ``includes`` so the shared cross-library test vectors can
    assert on the bucket itself.
    """
    data = f"{evaluation_key}:{targeting_key}".encode()
    return murmur3_x86_32(data) % 100 + 1


def murmur3_x86_32(data: bytes, seed: int = 0) -> int:
    """MurmurHash3 x86_32 of ``data``, as an unsigned 32-bit integer.

    Written out rather than taken from ``mmh3`` so the provider doesn't need a
    native wheel. The blocks are read little-endian, as every provider does.
    """
    hash_ = seed & _MASK_32
    block_end = len(data) - len(data) % 4

    for start in range(0, block_end, 4):
        k = int.from_bytes(data[start : start + 4], "little")
        hash_ ^= _mix_k(k)
        hash_ = _rotl32(hash_, 13)
        hash_ = (hash_ * 5 + 0xE6546B64) & _MASK_32

    tail = data[block_end:]
    if tail:
        hash_ ^= _mix_k(int.from_bytes(tail, "little"))

    hash_ ^= len(data) & _MASK_32
    return _fmix32(hash_)


def _mix_k(k: int) -> int:
    k = (k * _C1) & _MASK_32
    k = _rotl32(k, 15)
    return (k * _C2) & _MASK_32


def _rotl32(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (32 - shift))) & _MASK_32


def _fmix32(hash_: int) -> int:
    hash_ ^= hash_ >> 16
    hash_ = (hash_ * 0x85EBCA6B) & _MASK_32
    hash_ ^= hash_ >> 13
    hash_ = (hash_ * 0xC2B2AE35) & _MASK_32
    hash_ ^= hash_ >> 16
    return hash_
