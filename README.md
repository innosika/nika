# Лабораторные работы по ТиИСПИС — вариант «Космос»

БГУИР, группа 321702, 2025/2026 учебный год. Дисциплина «Технологии и инструментальные средства проектирования
интеллектуальных систем». Работы выполнены на системе NIKA (форк [ostis-apps/nika](https://github.com/ostis-apps/nika)).

**Бригада:** Пикта Игнат Дмитриевич, Переверзев Марат Атаджанович.

## Что сделано

| Работа | Содержание | Где в репозитории |
|---|---|---|
| ЛР1. Формализация предметной области | Предметная область «Космос»: 44 понятия (26 классов и 18 отношений), 46 экземпляров: планеты, спутники, звёзды, созвездия, космические аппараты и миссии, космонавты | `knowledge-base/extra/section_subject_domain_of_cosmos/` (`concepts/`, `relations/`) |
| ЛР2. Обучение классификатора сообщений | 6 классов вопросов, по 3 на каждого участника; сущности — понятия ЛР1; признак «эмоциональная окраска»; обучающие фразы в формате экспорта Wit.ai | `…/dialogue/`, `…/classification/` |
| ЛР3. Логические правила и фразы ответа | 6 классов ответных фраз, 31 логическое правило ответа, 77 фраз (65 с шаблонами); составной ответ на грубое сообщение | `…/answers/` (`phrases/`, `rules/`) |
| ЛР4. Модуль адаптации знаний | агенты загружают сведения о космических объектах из Wikidata (SPARQL, RDF), погружают в базу знаний и выводят новые знания по 4 логическим правилам; два режима: по запросу и наполнение базы знаний (в том числе заданного типа) | `problem-solver/py/modules/spaceImportModule/`, `problem-solver/cxx/space-knowledge-module/`, `…/knowledge_import/` |

**Кто что делал (ЛР2 и ЛР3 — одни и те же темы вопросов и ответов):**

| Участник | Классы вопросов и ответов |
|---|---|
| Пикта Игнат Дмитриевич | орбита (вокруг чего обращается объект), спутники, физические характеристики |
| Переверзев Марат Атаджанович | открытие объекта, созвездие, космическая миссия |

ЛР1 бригада выполняла совместно.

**ЛР4 (вариант согласован с преподавателем):**

| Участник | Режим | Агент |
|---|---|---|
| Пикта Игнат Дмитриевич | 1 — дозагрузка сведений об объекте по запросу пользователя | `SpaceOnDemandImportAgent` (Python) |
| Переверзев Марат Атаджанович | 2 — наполнение базы знаний космическими объектами (без типа, по классу, спутники объекта) | `SpaceKbFillAgent` (Python) |
| бригада | вывод новых знаний (scl-machine) | `SpaceKnowledgeInferenceAgent` (C++) |

Агенты встроены в программу обработки сообщения (`message_processing_program.gwf`) после агента погоды. Примеры: «Какие спутники есть у Сатурна?», «Наполни базу знаний небесными телами из Wikidata», «Наполни базу знаний спутниками Юпитера», «Какие тела входят в Солнечную систему?».

## Отчёты

Папка [`reports/`](reports/): `Отчёт_ЛР1_Космос.pdf`, `Отчёт_ЛР2_Космос.docx`, `Отчёт_ЛР3_Космос.docx`, `Отчёт_ЛР4_Космос.docx`.

## Изменения в самой NIKA (общие с вариантом «Медицина»)

- Облачный Wit.ai не используется: своё приложение в нём создать нельзя. Вместо него сделан **`wit-local/`** —
  локальный сервис, совместимый с Wit.ai (FastAPI, порт 8095). Словарь сущностей он берёт из базы знаний, а
  обучающие фразы — из `knowledge-base/extra/*/classification/`. В `nika.ini` указано `url = http://wit-local:8095/message`.
- `StandardMessageReplyAgent.cpp` — ответ по умолчанию ронял sc-server битой строкой UTF-8.
- `PhraseGenerationAgent.cpp` — проверка согласованности результатов поиска по шаблону фразы и новая переменная
  шаблона `$list{_x}`: выводит все значения через запятую.
- `Dockerfile`, `conanfile.py` — sc-machine и scl-machine берутся из релизов GitHub (conan.ostis.net недоступен).

## Запуск

```sh
make up        # sc-web http://localhost:8000, диалоговый интерфейс http://localhost:3033, wit-local http://localhost:8095
make kb        # пересобрать базу знаний после правок
curl -X POST localhost:8095/api/reload   # перечитать словарь сущностей и обучающие фразы wit-local
make down
```

Проверено: каждое правило применимо (33 из 33 ответов, все 31 правило), каждая фраза × объект — 4680 из 4680,
«Что такое …?» — 90 из 90.

---

<h1 align="center">Welcome to NIKA 👋</h1>
<p>
  <a href="https://www.gnu.org/licenses/gpl-3.0.html" target="_blank">
    <img alt="GPLv3" src="https://img.shields.io/badge/License-GPLv3-yellow.svg" />
  </a>
</p>

> **N**IKA is an **I**ntelligent **K**nowledge-driven **A**ssistant

## About
NIKA is an ostis-system designed with [OSTIS Technology principles](https://github.com/ostis-ai) in mind. 

You can learn more about it by asking the assistant: "What's NIKA?"

## Run documentation

```sh
#Terminal
cd nika
pip3 install mkdocs markdown-include mkdocs-material mkdocs-i18n
mkdocs serve
```

Then open http://127.0.0.1:9001/ in your browser

## ✨ Demo
![demo.png](docs/images/demo.png)


## Requirements
You will need [Docker](https://docs.docker.com/) (with Compose plugin) installed and running on your machine. 

We recommend using Docker Desktop on [macOS](https://docs.docker.com/desktop/install/mac-install/) / [Windows](https://docs.docker.com/desktop/install/windows-install/) and using [Docker Server](https://docs.docker.com/engine/install/#server) distribution for your Linux distribution of choice. Use installation instructions provided in the links above.
## Installation

```sh
git clone -c core.longpaths=true -c core.autocrlf=true https://github.com/ostis-apps/nika
cd nika
git submodule update --init --recursive
docker compose pull
docker compose build problem-solver
```

The `problem-solver` image is not published on Docker Hub, so `docker compose pull`
skips it and it has to be built locally once (this takes a while — it is a C++ build).

## 🚀 Usage
- Launch
  ```sh
  docker compose up --no-build
  ```
    This command will launch 2 Web UIs on your machine: 
  - sc-web - `localhost:8000`
  - dialogue web UI - `localhost:3033`

We've set our system to rebuild KB on each restart. If you're debugging some specific subset of your knowledge base you may want to change repo.path to exclude the folders you don't need. 

If you do not want to rebuild KB on relaunch, you can comment out the `REBUILD_KB` environment variable in `docker-compose.yml`.
You can use `docker compose run machine build` to rebuild KB manually.

## Author

* Website: [sem.systems](https://sem.systems/)
* GitHub: [@ostis-apps](https://github.com/ostis-apps), [@ostis-ai](https://github.com/ostis-ai)

## Show your support

Give us a ⭐️ if you've liked this project!

## Troubleshooting
Windows-specific problems:
- Docker images built on your computer are not launching correctly and logging something along these lines: `bash\r: No such file or directory`
  
  **Solution**: please make sure your Git repo is configured to be compatible UNIX line endings
  ```sh
  cd nika
  git config --local core.autocrlf true
  ```
- Git cannot clone repos or submodules, error looks like `error: unable to create file ... (file too long)`

  **Solution**: please make sure your Git repo has `longpaths` config option enabled:
  ```sh
  cd nika
  git config --local core.longpaths true
  ```
Common issues:
- `docker compose pull` fails with `failed to resolve reference "docker.io/ostis/nika:0.2.2": not found`

  **Solution**: this image is not published on Docker Hub — it is built from this repository. Build it once with `docker compose build problem-solver`, then launch as usual. The `problem-solver` service is marked `pull_policy: build`, so an up-to-date checkout skips it during `docker compose pull` instead of failing.

- The `problem-solver` build fails with `ERROR: Package 'sc-machine/0.10.4' not resolved: ...` (`certificate has expired` or `Connection to conan.ostis.net timed out`)

  The `sc-machine` and `scl-machine` Conan packages are only hosted on `conan.ostis.net` (they are not on conancenter). Its TLS certificate expired on 2026-08-08, and since September 2026 the server does not accept connections at all.

  **Solution**: by default the Docker build no longer uses that server (`OSTIS_DEPS=release`): sc-machine and scl-machine are taken from their GitHub release archives, and the modules are compiled against the same binaries they later run with. Only conancenter is needed. If you see this error, your checkout predates that change. To go back to the upstream Conan way once the server works again:
  ```sh
  OSTIS_DEPS=conan docker compose build problem-solver
  # while the certificate is expired:
  OSTIS_DEPS=conan CONAN_INSECURE_REMOTE=1 docker compose build problem-solver
  ```
  Note the trade-off: with `CONAN_INSECURE_REMOTE=1` the dependencies are downloaded over a TLS connection that is not verified, so a man-in-the-middle could substitute the packages your image is built from. Use it only if you accept that risk, and drop it once the certificate is valid again.

- Docker images cannot be built locally. Error: `status: the --mount option requires BuildKit` 
  
  **Solution**: Building `problem-solver` requires BuildKit (the Dockerfile uses a cache mount). Use the [Docker Docs BuildKit reference](https://docs.docker.com/go/buildkit) to enable Docker BuildKit on your computer. **In case you're using Windows**, you could use `$env:DOCKER_BUILDKIT = 1` while building in PowerShell.

- Help! My problem-solver container is `unhealthy`
  
  Looks like your container didn't start properly. There are two main reasons for this: violated `start_period` (in case it naturally takes a lot of time to launch our system on your hardware) or faulty server instance. Since there are 2 reasons to this problem, we'll provide 2 solutions. 
  
  **Solution 1**: Increasing `start_period` in `docker-compose.yml` might help you.

  **Solution 2**: Check [known issues](https://github.com/ostis-apps/nika/issues), and in case your problem is not reported yet, create a new one! 


## 🤝 Contributing

Contributions, issues and feature requests are welcome!<br />Feel free to check [issues page](https://github.com/ostis-apps/nika/issues). 

## 📝 License

This project is [GPLv3](https://www.gnu.org/licenses/gpl-3.0.html) licensed.
