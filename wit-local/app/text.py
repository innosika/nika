"""Токенизация и морфологическая нормализация русского текста.

Каждому токену сопоставляется множество нормальных форм (по всем разборам pymorphy3),
поэтому «лёгких» совпадает и с «лёгкое» (орган), и с «лёгкий» (прилагательное):
сущность из словаря найдётся при любом падеже, в котором её написал пользователь.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import pymorphy3

_morph = pymorphy3.MorphAnalyzer()

# Слово (буквы, цифры, дефис внутри) или отдельная звёздочка: «симптом*» — отношение.
TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+(?:[-‐][0-9A-Za-zА-Яа-яЁё]+)*|\*")


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int

    @property
    def lower(self) -> str:
        return normalize(self.text)


def normalize(word: str) -> str:
    return word.lower().replace("ё", "е").replace("‐", "-")


def tokenize(text: str) -> list[Token]:
    return [Token(m.group(0), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]


@lru_cache(maxsize=65536)
def norm_forms(word: str) -> frozenset[str]:
    """Все нормальные формы слова (плюс само слово в нижнем регистре)."""
    w = normalize(word)
    if w == "*" or not re.search(r"[а-я]", w):
        return frozenset({w})
    forms = {w}
    # «Аполлона-11», «Вояджером-1»: склоняется слово перед дефисом, номер не меняется
    m = re.fullmatch(r"([а-я]+)-(\d+)", w)
    if m:
        return frozenset(f"{f}-{m.group(2)}" for f in norm_forms(m.group(1)))
    for p in _morph.parse(w):
        forms.add(normalize(p.normal_form))
    return frozenset(forms)


@lru_cache(maxsize=65536)
def lemma(word: str) -> str:
    """Наиболее вероятная нормальная форма — для признаков классификатора."""
    w = normalize(word)
    if not re.search(r"[а-я]", w):
        return w
    return normalize(_morph.parse(w)[0].normal_form)


def edit_distance_le1(a: str, b: str) -> bool:
    """Расстояние Дамерау–Левенштейна не больше 1 (опечатка: замена, вставка, удаление, перестановка)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        if len(diff) == 1:
            return True
        return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
    if la > lb:
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]
