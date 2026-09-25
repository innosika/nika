# wit-local — локальный Wit.ai-совместимый классификатор сообщений NIKA

Замена облачного сервиса [wit.ai](https://wit.ai) для лабораторных работ по ТиИСПИС
(ЛР2 «Обучение классификатора сообщений», ЛР3). Облачное приложение Wit.ai создать
нельзя (вход только через учётную запись Meta), а приложение с токеном по умолчанию из
`nika.ini` принадлежит разработчикам NIKA и не обучается своими фразами.

Агент `MessageTopicClassificationAgent` (C++, `WitAiClient.cpp`) отправляет текст
сообщения запросом `GET <url>?q=<текст>` и разбирает JSON с полями `intents`,
`entities`, `traits`. wit-local отвечает в том же формате, поэтому код NIKA не меняется —
достаточно адреса в `nika.ini`:

```ini
[wit-ai]
url = http://wit-local:8095/message
```

## Как устроено

| Часть | Что делает |
|---|---|
| `app/gazetteer.py` | словарь сущностей: через sc-server читает элементы `concept_wit_entity`, их основные и дополнительные идентификаторы (ru/en), классы и максимальный класс ветки иерархии. Кэш — `/data/gazetteer.json`. Сверка с БЗ каждые `REFRESH_SECONDS` |
| `app/text.py` | токенизация, нормальные формы pymorphy3 (все разборы слова), опечатки (расстояние ≤ 1) |
| `app/dataset.py` | чтение обучающих фраз в формате экспорта Wit.ai из `knowledge-base/extra/*/classification/` |
| `app/nlu.py` | поиск сущностей → замена упоминаний типом (`ent_concept_disease`) → TF-IDF (леммы, биграммы, символьные n-граммы, набор типов сущностей) → логистическая регрессия для намерения и признака `wit$sentiment`; порог уверенности; оценка качества |
| `app/server.py` | FastAPI: `GET /message` (формат Wit.ai), `/health`, `/api/info`, `/api/entities`, `/api/history`, `POST /api/reload`, тестовая страница `/` |
| `app/static/index.html` | аналог раздела Understanding в Wit.ai: разбор фразы, намерения, словарь сущностей, качество, журнал запросов NIKA |

Значение (`value`) сущности в ответе — всегда основной русский идентификатор элемента
базы знаний: агент NIKA сопоставляет сущность с `concept_wit_entity` именно по нему.
Поэтому «Нурофен» → ибупрофен, «гриппе» → грипп, «туберкулоз» (опечатка) → туберкулёз.

## Обучающие данные

Один классификатор обслуживает все предметные области: читаются все каталоги
`knowledge-base/extra/*/classification/`:

```
classification/
  app.json, intents/*.json, entities/rrel_entity.json, traits/wit$sentiment.json
  utterances/utterances-1.json     обучающие фразы (разметка: intent, entities с start/end/body/value, traits)
  test/utterances-dev.json         валидационная выборка
  test/utterances-test.json        итоговая тестовая выборка (при настройке не использовалась)
```

Общие для всех вариантов фразы (приветствие, навыки, лабораторные, погода, фразы вне тем)
и формализация признака `wit$sentiment` — в `knowledge-base/extra/local_message_classifier/`,
генератор — `tools/gen_base_classification.py`.

## Запуск

Сервис входит в `docker-compose.yml` NIKA и поднимается вместе с ней (`make up`).
Тестовая страница: http://localhost:8095. После изменения обучающих фраз или БЗ:

```bash
curl -X POST http://localhost:8095/api/reload
```

## Инструменты (`tools/`)

- `evaluate.py` — перекрёстная проверка и качество на выборках без запуска сервиса:
  `python3 tools/evaluate.py --splits dev,test --domain section_subject_domain_of_medicine`
- `nika_dialog.py` — диалог с NIKA из командной строки (как веб-интерфейс) с печатью классов
  сообщения, сущностей и ответа: `python3 tools/nika_dialog.py "Что такое грипп?"`
- `witformat.py` — склонение названий понятий и запись экспорта Wit.ai (для генераторов фраз).

Зависимости для запуска инструментов вне контейнера: `pip install -r requirements.txt`.
