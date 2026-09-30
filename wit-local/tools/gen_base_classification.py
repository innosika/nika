"""Обучающие фразы для стандартных классов сообщений NIKA (общие для всех предметных областей).

Пишет экспорт в формате Wit.ai в knowledge-base/extra/local_message_classifier/classification:
приветствия, вопросы о навыках системы, о лабораторных работах, о погоде, поиск слова
по букве, «Что такое Ника» и фразы вне всех намерений (класс none: на них сервис
не возвращает намерения, как Wit.ai при низкой уверенности).

Запуск:  python3 gen_base_classification.py [каталог knowledge-base]
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from witformat import render, with_coloring, write_export  # noqa: E402

KB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", "knowledge-base")
OUT = os.path.join(KB, "extra", "local_message_classifier", "classification")
rnd = random.Random(2)

GREETING = ["Привет", "Привет!", "Здравствуй", "Здравствуйте", "Здравствуйте, Ника", "Добрый день",
            "Добрый вечер", "Доброе утро", "Хай", "Приветствую", "Приветствую тебя, Ника", "Салют",
            "Привет, Ника!", "Здорово", "Доброго дня", "Хэй, привет", "Приветики", "Добрый день, Ника!",
            "Ника, привет", "Здравствуй, Ника", "Всем привет", "Привет, как дела?", "Хеллоу",
            "Доброй ночи", "Приветствую вас"]
SKILL = ["Что ты умеешь?", "Что ты можешь?", "Какие у тебя навыки?", "Чем ты можешь помочь?",
         "Что ты умеешь делать?", "Расскажи, что ты умеешь", "На что ты способна?",
         "Какие вопросы тебе можно задавать?", "С чем ты можешь помочь?", "Какие у тебя возможности?",
         "Что ты знаешь и умеешь?", "Чем ты полезна?", "Какие функции у тебя есть?",
         "О чём тебя можно спросить?", "Твои умения?", "Что ты вообще умеешь?", "Какие у тебя умения?",
         "Для чего ты нужна?", "Чем ты занимаешься?", "Какие задачи ты решаешь?"]
LABS = ["Лабораторная работа №1", "Лабораторная работа №2", "Лабораторная работа №3", "Лабораторная работа №4"]
LAB_COND = ["Какое условие {l:gent}?", "Какое задание у {l:gent}?", "Что нужно сделать в {l:loct}?",
            "Расскажи условие {l:gent}", "В чём заключается {l}?", "Какая цель у {l:gent}?",
            "Что требуется в {l:loct}?", "Какое задание в {l:loct}?", "Условие {l:gent}",
            "Что надо сделать по {l:datv}?"]
LAB_DEAD = ["Когда дедлайн {l:gent}?", "До какого числа сдать {l:accs}?", "Какой срок сдачи у {l:gent}?",
            "Когда нужно сдать {l:accs}?", "Какой дедлайн у {l:gent}?", "До какого срока сдаётся {l}?",
            "Когда последний день сдачи {l:gent}?", "Срок сдачи {l:gent}", "К какому числу сдать {l:accs}?"]
CITIES = ["Минск", "Брест", "Москва"]
WEATHER = ["Какая погода в {c:loct}?", "Какая сейчас погода в {c:loct}?", "Погода в {c:loct}",
           "Сколько градусов в {c:loct}?", "Холодно ли сейчас в {c:loct}?", "Какая температура в {c:loct}?",
           "Скажи погоду в {c:loct}", "Идёт ли дождь в {c:loct}?", "Как там погода в {c:loct}?",
           "Что с погодой в {c:loct}?", "Тепло ли в {c:loct}?", "Прогноз погоды для {c:gent}"]
LETTER = ["Что в {e:loct} начинается на букву А?", "Какие слова в {e:loct} начинаются на букву М?",
          "Найди в {e:loct} слово на букву А", "Что в {e:loct} на букву М?",
          "Какие слова на букву А есть в {e:loct}?", "Что начинается на букву М в {e:loct}?"]
NIKA = ["Что такое {n}?", "Кто такая {n}?", "Расскажи о {n:loct}", "Что ты знаешь о {n:loct}?",
        "Кто ты такая, {n}?", "Что представляет собой {n}?", "Опиши {n:accs}", "Кто такая {n}? Расскажи",
        "Что за система {n}?", "Дай определение {n:gent}"]
NONE = ["Сколько будет два плюс два?", "Расскажи анекдот", "Я люблю пиццу", "Который час?",
        "Какой сегодня день недели?", "Спой песню", "Ты умеешь танцевать?", "Как пройти в библиотеку?",
        "Сколько стоит билет в кино?", "Мне скучно", "Включи музыку", "Поставь будильник на семь утра",
        "Кто выиграл вчерашний матч?", "Купи мне хлеба", "Какой курс доллара?", "Переведи на английский слово кошка",
        "Я пошёл спать", "ааааа", "фывапролд", "123456", "ну и ладно", "ок", "понятно", "ясно",
        "Как зовут президента Франции?", "Посоветуй фильм", "Закажи такси", "Напиши стихотворение",
        "Сколько тебе лет?", "Какого цвета небо?", "Где купить машину?", "Что приготовить на ужин?",
        "Мой кот спит на диване", "Хорошая сегодня погода, правда", "Хочу в отпуск"]

POSITIVE_ONLY = ["Спасибо большое!", "Спасибо, ты очень помогла", "Благодарю за помощь", "Ты молодец, спасибо",
                 "Огромное спасибо!", "Спасибо, всё понятно", "Благодарю!", "Ты лучшая, спасибо!",
                 "Большое спасибо за ответ", "Спасибо, очень полезно"]
NEGATIVE_ONLY = ["Ты ничего не понимаешь", "Ужасный ответ", "Опять ерунду говоришь", "Бесполезная система",
                 "Отвечаешь невпопад", "Это полный бред", "Ты тупая", "Надоело, ничего не работает",
                 "Что за чушь ты несёшь", "Хватит тормозить"]


def items(intent, templates, slot=None, values=()):
    out = []
    for t in templates:
        if slot:
            for v in values:
                out.append(dict(render(t, {slot: v}), intent=intent))
        else:
            out.append({"text": t, "entities": [], "intent": intent})
    return out


def color(pool, share=0.35):
    """Часть фраз снабжается вежливой или грубой рамкой — это обучающие примеры признака wit$sentiment."""
    out = []
    for it in pool:
        c = "neutral"
        r = rnd.random()
        if r < share / 2:
            c = "positive"
        elif r < share:
            c = "negative"
        u = with_coloring(it, c, rnd)
        out.append({"text": u["text"], "entities": u["entities"], "intent": it["intent"],
                    "traits": {"wit$sentiment": c}})
    return out


def main():
    pool = []
    pool += items("about_skill", SKILL)
    pool += items("about_lab_work_condition", LAB_COND, "l", LABS)
    pool += items("about_lab_work_deadline", LAB_DEAD, "l", LABS)
    pool += items("about_weather", WEATHER, "c", CITIES)
    pool += items("about_letter_search", LETTER, "e", ["Пример"])
    pool += items("about_entity", NIKA, "n", ["Ника"])
    train = [dict(it, traits={"wit$sentiment": "neutral"}) for it in items("greeting", GREETING)]
    train += color(pool)
    train += [{"text": t, "entities": [], "intent": "none", "traits": {"wit$sentiment": "neutral"}} for t in NONE]
    train += [{"text": t, "entities": [], "intent": "none", "traits": {"wit$sentiment": "positive"}} for t in POSITIVE_ONLY]
    train += [{"text": t, "entities": [], "intent": "none", "traits": {"wit$sentiment": "negative"}} for t in NEGATIVE_ONLY]

    # Валидационная выборка: формулировки, которых нет среди шаблонов обучения.
    test = [
        {"text": "Приветик!", "intent": "greeting"},
        {"text": "Доброго вечера, Ника", "intent": "greeting", "entities": [("Ника", "Ника")]},
        {"text": "Здравствуйте, уважаемая система", "intent": "greeting"},
        {"text": "Какими навыками ты обладаешь?", "intent": "about_skill"},
        {"text": "Что ты умеешь, Ника?", "intent": "about_skill", "entities": [("Ника", "Ника")]},
        {"text": "Скажи, какие есть у тебя способности", "intent": "about_skill"},
        {"text": "Сколько сейчас градусов в Москве?", "intent": "about_weather",
         "entities": [("Москве", "Москва")]},
        {"text": "Будет ли дождь в Минске?", "intent": "about_weather", "entities": [("Минске", "Минск")]},
        {"text": "Когда сдавать лабораторную работу №2?", "intent": "about_lab_work_deadline",
         "entities": [("лабораторную работу №2", "Лабораторная работа №2")]},
        {"text": "Что надо сделать в лабораторной работе №3?", "intent": "about_lab_work_condition",
         "entities": [("лабораторной работе №3", "Лабораторная работа №3")]},
        {"text": "Кто ты, Ника?", "intent": "about_entity", "entities": [("Ника", "Ника")]},
        {"text": "Посоветуй хорошую книгу", "intent": "none"},
        {"text": "Сколько километров до Луны пешком?", "intent": "none", "entities": [("Луны", "Луна")]},
        {"text": "Спасибо тебе огромное!", "intent": "none", "sentiment": "positive"},
        {"text": "Подскажите, пожалуйста, что вы умеете?", "intent": "about_skill", "sentiment": "positive"},
        {"text": "Ну и что ты вообще умеешь, а?", "intent": "about_skill", "sentiment": "negative"},
    ]
    test_items = []
    for t in test:
        ents = []
        for body, value in t.get("entities", []):
            s = t["text"].index(body)
            ents.append({"entity": "rrel_entity:rrel_entity", "start": s, "end": s + len(body),
                         "body": body, "value": value, "entities": []})
        test_items.append({"text": t["text"], "intent": t["intent"], "entities": ents,
                           "traits": {"wit$sentiment": t.get("sentiment", "neutral")}})

    intents = sorted({u["intent"] for u in train if u["intent"] != "none"})
    write_export(OUT, "nika_base", intents, train, dev=test_items,
                 traits={"wit$sentiment": ["positive", "neutral", "negative"]})
    print(f"base: {len(train)} обучающих фраз, {len(test_items)} валидационных, намерения: {', '.join(intents)} -> {OUT}")


if __name__ == "__main__":
    main()
