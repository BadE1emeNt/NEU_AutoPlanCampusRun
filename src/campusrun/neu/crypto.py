"""纯 Python 的 AES-128-CBC / RSA PKCS#1 v1.5，用于校园乐跑接口与 CAS 登录。

不依赖第三方包，便于在 Windows 上直接运行。
"""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# AES-128
# ---------------------------------------------------------------------------
def _gmul(a: int, b: int) -> int:
    result = 0
    for _ in range(8):
        if b & 1:
            result ^= a
        high = a & 0x80
        a = (a << 1) & 0xFF
        if high:
            a ^= 0x1B
        b >>= 1
    return result


def _rotl8(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (8 - shift))) & 0xFF


def _build_sbox() -> tuple[list[int], list[int]]:
    sbox = [0] * 256
    for value in range(256):
        if value == 0:
            inverse = 0
        else:
            inverse = 0
            for candidate in range(1, 256):
                if _gmul(value, candidate) == 1:
                    inverse = candidate
                    break
        sbox[value] = (
            inverse
            ^ _rotl8(inverse, 1)
            ^ _rotl8(inverse, 2)
            ^ _rotl8(inverse, 3)
            ^ _rotl8(inverse, 4)
            ^ 0x63
        )
    inv = [0] * 256
    for index, value in enumerate(sbox):
        inv[value] = index
    return sbox, inv


_SBOX, _INV_SBOX = _build_sbox()
_RCON = [0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def _expand_key(key: bytes) -> list[list[int]]:
    if len(key) != 16:
        raise ValueError("AES-128 需要 16 字节密钥")
    words = [list(key[index : index + 4]) for index in range(0, 16, 4)]
    for index in range(4, 44):
        temp = words[index - 1][:]
        if index % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[value] for value in temp]
            temp[0] ^= _RCON[index // 4]
        words.append([words[index - 4][j] ^ temp[j] for j in range(4)])
    return [sum(words[round_no * 4 : round_no * 4 + 4], []) for round_no in range(11)]


def _add_round_key(state: list[int], round_key: list[int]) -> None:
    for index in range(16):
        state[index] ^= round_key[index]


def _sub_bytes(state: list[int]) -> None:
    for index in range(16):
        state[index] = _SBOX[state[index]]


def _inv_sub_bytes(state: list[int]) -> None:
    for index in range(16):
        state[index] = _INV_SBOX[state[index]]


def _shift_rows(state: list[int]) -> None:
    # state index = 4 * column + row
    for row in range(1, 4):
        values = [state[4 * column + row] for column in range(4)]
        for column in range(4):
            state[4 * column + row] = values[(column + row) % 4]


def _inv_shift_rows(state: list[int]) -> None:
    for row in range(1, 4):
        values = [state[4 * column + row] for column in range(4)]
        for column in range(4):
            state[4 * column + row] = values[(column - row) % 4]


def _mix_columns(state: list[int]) -> None:
    for column in range(4):
        index = 4 * column
        a0, a1, a2, a3 = state[index : index + 4]
        state[index + 0] = _gmul(a0, 2) ^ _gmul(a1, 3) ^ a2 ^ a3
        state[index + 1] = a0 ^ _gmul(a1, 2) ^ _gmul(a2, 3) ^ a3
        state[index + 2] = a0 ^ a1 ^ _gmul(a2, 2) ^ _gmul(a3, 3)
        state[index + 3] = _gmul(a0, 3) ^ a1 ^ a2 ^ _gmul(a3, 2)


def _inv_mix_columns(state: list[int]) -> None:
    for column in range(4):
        index = 4 * column
        a0, a1, a2, a3 = state[index : index + 4]
        state[index + 0] = _gmul(a0, 14) ^ _gmul(a1, 11) ^ _gmul(a2, 13) ^ _gmul(a3, 9)
        state[index + 1] = _gmul(a0, 9) ^ _gmul(a1, 14) ^ _gmul(a2, 11) ^ _gmul(a3, 13)
        state[index + 2] = _gmul(a0, 13) ^ _gmul(a1, 9) ^ _gmul(a2, 14) ^ _gmul(a3, 11)
        state[index + 3] = _gmul(a0, 11) ^ _gmul(a1, 13) ^ _gmul(a2, 9) ^ _gmul(a3, 14)


def _encrypt_block(block: bytes, round_keys: list[list[int]]) -> bytes:
    state = list(block)
    _add_round_key(state, round_keys[0])
    for round_no in range(1, 10):
        _sub_bytes(state)
        _shift_rows(state)
        _mix_columns(state)
        _add_round_key(state, round_keys[round_no])
    _sub_bytes(state)
    _shift_rows(state)
    _add_round_key(state, round_keys[10])
    return bytes(state)


def _decrypt_block(block: bytes, round_keys: list[list[int]]) -> bytes:
    state = list(block)
    _add_round_key(state, round_keys[10])
    for round_no in range(9, 0, -1):
        _inv_shift_rows(state)
        _inv_sub_bytes(state)
        _add_round_key(state, round_keys[round_no])
        _inv_mix_columns(state)
    _inv_shift_rows(state)
    _inv_sub_bytes(state)
    _add_round_key(state, round_keys[0])
    return bytes(state)


def _pad(data: bytes) -> bytes:
    padding = 16 - (len(data) % 16)
    return data + bytes([padding]) * padding


def _unpad(data: bytes) -> bytes:
    if not data:
        raise ValueError("空数据")
    padding = data[-1]
    if padding < 1 or padding > 16 or data[-padding:] != bytes([padding]) * padding:
        raise ValueError("AES 填充无效")
    return data[:-padding]


def aes_cbc_encrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    if len(iv) != 16:
        raise ValueError("AES-CBC 需要 16 字节 IV")
    round_keys = _expand_key(key)
    padded = _pad(data)
    output = bytearray()
    previous = iv
    for offset in range(0, len(padded), 16):
        block = bytes(a ^ b for a, b in zip(padded[offset : offset + 16], previous))
        encrypted = _encrypt_block(block, round_keys)
        output.extend(encrypted)
        previous = encrypted
    return bytes(output)


def aes_cbc_decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    if len(iv) != 16:
        raise ValueError("AES-CBC 需要 16 字节 IV")
    if not data or len(data) % 16:
        raise ValueError("AES-CBC 密文长度无效")
    round_keys = _expand_key(key)
    output = bytearray()
    previous = iv
    for offset in range(0, len(data), 16):
        block = data[offset : offset + 16]
        decrypted = _decrypt_block(block, round_keys)
        output.extend(bytes(a ^ b for a, b in zip(decrypted, previous)))
        previous = block
    return _unpad(bytes(output))


def aes_encrypt_base64(text: str, key: bytes, iv: bytes) -> str:
    return base64.b64encode(aes_cbc_encrypt(text.encode("utf-8"), key, iv)).decode("ascii")


def aes_decrypt_base64(data: str, key: bytes, iv: bytes) -> str:
    return aes_cbc_decrypt(base64.b64decode(data), key, iv).decode("utf-8")


# ---------------------------------------------------------------------------
# RSA 公钥解析 / PKCS#1 v1.5 加密
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class RSAPublicKey:
    n: int
    e: int

    @property
    def size_bytes(self) -> int:
        return (self.n.bit_length() + 7) // 8


def _read_tlv(data: bytes, offset: int) -> tuple[int, bytes, int]:
    if offset + 2 > len(data):
        raise ValueError("DER 数据不完整")
    tag = data[offset]
    length = data[offset + 1]
    offset += 2
    if length & 0x80:
        length_bytes = length & 0x7F
        if length_bytes == 0 or offset + length_bytes > len(data):
            raise ValueError("DER 长度无效")
        length = int.from_bytes(data[offset : offset + length_bytes], "big")
        offset += length_bytes
    if offset + length > len(data):
        raise ValueError("DER 内容不完整")
    return tag, data[offset : offset + length], offset + length


def _parse_public_key_der(der: bytes) -> RSAPublicKey:
    tag, content, _ = _read_tlv(der, 0)
    if tag != 0x30:
        raise ValueError("不是 SubjectPublicKeyInfo")
    # AlgorithmIdentifier
    tag, _, inner = _read_tlv(content, 0)
    if tag != 0x30:
        raise ValueError("缺少算法标识")
    # BIT STRING
    tag, bit_string, _ = _read_tlv(content, inner)
    if tag != 0x03 or not bit_string:
        raise ValueError("缺少公钥 BIT STRING")
    tag, rsa_seq, _ = _read_tlv(bit_string, 1)
    if tag != 0x30:
        raise ValueError("公钥结构无效")
    tag, modulus, offset = _read_tlv(rsa_seq, 0)
    if tag != 0x02:
        raise ValueError("缺少模数")
    tag, exponent, _ = _read_tlv(rsa_seq, offset)
    if tag != 0x02:
        raise ValueError("缺少指数")
    return RSAPublicKey(
        n=int.from_bytes(modulus.lstrip(b"\x00"), "big"),
        e=int.from_bytes(exponent.lstrip(b"\x00"), "big"),
    )


def parse_rsa_public_key(pem_or_base64: str) -> RSAPublicKey:
    text = pem_or_base64.strip()
    text = re.sub(r"-----BEGIN [^-]+-----", "", text)
    text = re.sub(r"-----END [^-]+-----", "", text)
    text = re.sub(r"\s+", "", text)
    try:
        der = base64.b64decode(text, validate=True)
    except ValueError as exc:
        raise ValueError("RSA 公钥不是合法 Base64") from exc
    return _parse_public_key_der(der)


def rsa_encrypt_pkcs1v15(message: str | bytes, key: RSAPublicKey) -> bytes:
    data = message.encode("utf-8") if isinstance(message, str) else message
    size = key.size_bytes
    if len(data) > size - 11:
        raise ValueError("RSA 明文过长")
    padding = bytearray()
    while len(padding) < size - 3 - len(data):
        byte = os.urandom(1)[0]
        if byte != 0:
            padding.append(byte)
    encoded = b"\x00\x02" + bytes(padding) + b"\x00" + data
    number = pow(int.from_bytes(encoded, "big"), key.e, key.n)
    return number.to_bytes(size, "big")


def rsa_encrypt_base64(message: str | bytes, public_key: str) -> str:
    key = parse_rsa_public_key(public_key)
    return base64.b64encode(rsa_encrypt_pkcs1v15(message, key)).decode("ascii")
