"""Соответствие свойств и классов Wikidata отношениям и классам базы знаний «Космос», формат значений.

Значения в базе знаний ЛР1 — русские текстовые ссылки («5,68·10^26 кг», «60 268 км», «29,46 года»,
«8 января 1610 года»), связи между объектами — узлы. Импорт пишет в том же формате, поэтому правила и фразы
ЛР3 отвечают по загруженным сведениям без изменений.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

# --- свойства Wikidata
# значение — объект: отношение и класс, в который создаётся новый узел (None — класс по типу Wikidata)
NODE_PROPS = {
    "P397": ("nrel_orbit", None),                              # родительское тело (вокруг чего обращается)
    "P59": ("nrel_located_in_constellation", "concept_constellation"),
    "P137": ("nrel_operator", "concept_space_agency"),
    "P1029": ("nrel_mission_crew", "concept_cosmonaut"),
    "P448": ("nrel_launch_site", "concept_cosmodrome"),
    "P375": ("nrel_used_launch_vehicle", "concept_launch_vehicle"),
}
# значение — объект, но в базе знаний хранится его название текстом (как в ЛР1)
LABEL_PROPS = {"P61": "nrel_discoverer", "P215": "nrel_spectral_class"}
QUANTITY_PROPS = {"P2067": "nrel_mass", "P2120": "nrel_equatorial_radius", "P2146": "nrel_orbital_period"}
TIME_PROPS = {"P575": "nrel_discovery_date", "P619": "nrel_launch_date", "P580": "nrel_start_date"}


@dataclass
class WdClass:
    qid: str
    ru: str
    kb_class: str
    pattern: str = ""          # особый запрос состава класса для режима 2 (иначе — экземпляры подклассов)


# Самые известные звёзды (запрос по звёздам Wikidata — 32 с; выполнен один раз, 29.09.2026)
KNOWN_STARS = ["Q3409", "Q12176", "Q12124", "Q3427", "Q12189", "Q12126", "Q12985", "Q12166", "Q12975", "Q12970",
               "Q13034", "Q12179", "Q13008", "Q12183"]

# Порядок — от частного к общему: объекту присваивается первый подходящий класс.
CLASSES = [
    WdClass("Q1319599", "ледяной гигант", "concept_gas_giant", "?x wdt:P31/wdt:P279* wd:Q1319599 ; wdt:P397 wd:Q525 ."),
    WdClass("Q121750", "газовая планета", "concept_gas_giant", "?x wdt:P31/wdt:P279* wd:Q121750 ; wdt:P397 wd:Q525 ."),
    WdClass("Q3504248", "внутренняя планета", "concept_terrestrial_planet"),
    WdClass("Q2199", "карликовая планета", "concept_dwarf_planet"),
    WdClass("Q2537", "естественный спутник", "concept_natural_satellite"),
    WdClass("Q3559", "комета", "concept_comet", "?x wdt:P31/wdt:P279? wd:Q3559 ."),
    WdClass("Q3863", "астероид", "concept_asteroid", "?x wdt:P31 wd:Q3863 ; wdt:P397 wd:Q525 ."),
    WdClass("Q589", "чёрная дыра", "concept_black_hole", "?x wdt:P31/wdt:P279? wd:Q589 ."),
    WdClass("Q42372", "туманность", "concept_nebula", "?x wdt:P31/wdt:P279? wd:Q42372 ."),
    WdClass("Q318", "галактика", "concept_galaxy", "?x wdt:P31/wdt:P279 wd:Q318 ."),
    # звёзд в Wikidata миллионы: запрос самых известных не укладывается в отведённое время, поэтому список
    # известных звёзд хранится в базе знаний (nrel_known_wikidata_member у класса Wikidata «звезда»)
    WdClass("Q523", "звезда", "concept_star", "SEED"),
    WdClass("Q8928", "созвездие", "concept_constellation", "?x wdt:P31 wd:Q8928 ."),
    WdClass("Q25956", "орбитальная станция", "concept_space_station", "?x wdt:P31/wdt:P279? wd:Q25956 ."),
    WdClass("Q26529", "космический зонд", "concept_interplanetary_probe"),
    WdClass("Q26540", "искусственный спутник", "concept_artificial_satellite", "?x wdt:P31/wdt:P279? wd:Q26540 ."),
    WdClass("Q697175", "ракета-носитель", "concept_launch_vehicle", "?x wdt:P31/wdt:P279? wd:Q697175 . "
            "FILTER NOT EXISTS { ?x wdt:P31/wdt:P279* wd:Q40218 }"),
    WdClass("Q752783", "пилотируемый космический полёт", "concept_space_mission"),
    WdClass("Q2133344", "космическая миссия", "concept_space_mission", "?x wdt:P31/wdt:P279? wd:Q2133344 ."),
    WdClass("Q194188", "космодром", "concept_cosmodrome"),
    WdClass("Q17505024", "космическое агентство", "concept_space_agency", "?x wdt:P31/wdt:P279? wd:Q17505024 ."),
    WdClass("Q634", "планета", "concept_planet", "?x wdt:P31/wdt:P279* wd:Q634 ; wdt:P397 wd:Q525 ."),
]
BY_QID = {c.qid: c for c in CLASSES}

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]


def num(x: float, digits: int = 2) -> str:
    """Число по-русски: запятая, пробелы между тысячами."""
    s = f"{x:,.{digits}f}".replace(",", " ").replace(".", ",")
    return s.rstrip("0").rstrip(",") if "," in s else s


def mass(kg: float) -> str:
    exp = int(math.floor(math.log10(abs(kg)))) if kg else 0
    return f"{num(kg / 10 ** exp)}·10^{exp} кг" if exp >= 4 else f"{num(kg)} кг"


def radius(m: float) -> str:
    return f"{num(m / 1000, 0 if m >= 10_000 else 1)} км"


def plural(n: float, one: str, few: str, many: str) -> str:
    if n != int(n):
        return few
    n = int(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    return few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


def period(seconds: float) -> str:
    days = seconds / 86400
    if days >= 365.25:
        years = round(days / 365.25, 2)
        return f"{num(years)} {plural(years, 'год', 'года', 'лет')}"
    d = round(days, 2)
    return f"{num(d)} {plural(d, 'сутки', 'суток', 'суток')}"


def date(iso: str, precision: int) -> str:
    """«+1610-01-08T00:00:00Z», точность 11 → «8 января 1610 года». Непонятное значение (например,
    «неизвестное значение» Wikidata) → пустая строка, такая дата не погружается."""
    m_ = re.match(r"^([+-]?)(\d+)-(\d\d)-(\d\d)", iso or "")
    if not m_ or precision < 9:
        return ""
    bc, y, m, d = m_.group(1) == "-", m_.group(2), m_.group(3), m_.group(4)
    year = f"{int(y)} года" + (" до н. э." if bc else "")
    if precision >= 11:
        return f"{int(d)} {MONTHS[int(m) - 1]} {year}"
    if precision == 10:
        return f"{['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'][int(m) - 1]} {int(y)} года"
    return year


FORMAT = {"nrel_mass": mass, "nrel_equatorial_radius": radius, "nrel_orbital_period": period}
