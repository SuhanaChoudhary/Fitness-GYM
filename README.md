# ACEest Fitness & Gym — DevOps Delivery Pipeline

A Flask based fitness and gym management service for **ACEest Fitness & Gym**, delivered through a
complete DevOps lifecycle: local development → Git/GitHub → Pytest → Docker → GitHub Actions →
Jenkins BUILD quality gate.

[![ACEest Fitness CI](../../actions/workflows/main.yml/badge.svg)](../../actions/workflows/main.yml)

---

## 1. Overview

| Layer | Technology | Purpose |
| --- | --- | --- |
| Application | Flask 3 (Python 3.11) | Trainer dashboard + JSON API |
| Persistence | SQLite | Clients, progress, workouts, users |
| Tests | Pytest | 70 unit and integration tests |
| Container | Docker (multi-stage) | Reproducible, non-root runtime image |
| CI | GitHub Actions | Build, lint, Docker assembly, containerised tests |
| BUILD gate | Jenkins Pipeline | Clean rebuild + test execution from SCM |

### Functional scope

* Session based trainer login with hashed credentials and role awareness.
* Client profile management (age, height, weight, goals, membership).
* Fitness program catalogue with automatic **calorie target calculation** (`weight × program factor`).
* Deterministic **program recommendation** based on goal and experience level.
* **BMI** calculation and WHO classification.
* Weekly **adherence tracking** with averages and an on-track indicator.
* **Workout logging** with validated workout types and durations.
* **Membership status** derivation (Active / Expiring Soon / Expired / Inactive).
* Exportable JSON **client report**.
* `/health` endpoint used by Docker `HEALTHCHECK`, GitHub Actions and Jenkins smoke tests.

### Project structure

```text
.
├── app.py                      # Flask application factory, routes, request validation
├── fitness.py                  # Pure domain logic (no Flask / DB imports) — unit testable
├── models.py                   # SQLite data access layer (parameterised statements)
├── templates/                  # Jinja2 templates (base, login, dashboard, error)
├── static/                     # Dashboard CSS and JavaScript
├── tests/
│   ├── conftest.py             # Fixtures: isolated DB per test, authenticated client
│   ├── test_fitness.py         # Unit tests for business rules
│   └── test_app.py             # Integration tests for routes and the JSON API
├── Dockerfile                  # Multi-stage: builder → runtime → test
├── .dockerignore
├── Jenkinsfile                 # Declarative Jenkins BUILD pipeline
├── .github/workflows/main.yml  # GitHub Actions CI pipeline
├── requirements.txt            # Runtime dependencies
├── requirements-dev.txt        # Test/lint dependencies
├── pytest.ini / .flake8        # Tooling configuration
└── The code versions for DevOps Assignment/   # Original Tkinter prototypes (reference only)
```

---

## 2. Local setup and execution

### Prerequisites

* Python 3.9+ (3.11 recommended — matches the container image)
* Docker (optional, for the containerised workflow)

### Run the application

```bash
git clone <your-repository-url>
cd <repository>

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt

export ACEEST_SECRET_KEY="a-long-random-value"
export ACEEST_ADMIN_PASSWORD="ChooseAStrongPassword"

python app.py
```

Open <http://127.0.0.1:5000> and sign in with `admin` and the password exported above.

> The default admin account is seeded only when the `users` table is empty. If you start without
> `ACEEST_ADMIN_PASSWORD`, the development fallback `ChangeMe123!` is used — never deploy with it.

### Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `ACEEST_SECRET_KEY` | random per process | Flask session signing key (set it in production) |
| `ACEEST_DB_PATH` | `./aceest_fitness.db` | SQLite database location |
| `ACEEST_ADMIN_USER` | `admin` | Seeded administrator username |
| `ACEEST_ADMIN_PASSWORD` | `ChangeMe123!` | Seeded administrator password |
| `ACEEST_COOKIE_SECURE` | `0` | Set to `1` to serve session cookies over HTTPS only |
| `ACEEST_HOST` / `ACEEST_PORT` | `127.0.0.1` / `5000` | Dev server bind address |

### Production style run

```bash
gunicorn --bind 0.0.0.0:5000 --workers 2 "app:create_app()"
```

---

## 3. Running the tests manually

```bash
# Full suite
pytest

# Verbose with coverage
pytest -v --cov=. --cov-report=term-missing

# A single file or test
pytest tests/test_fitness.py
pytest tests/test_app.py::TestClientManagement::test_save_client_calculates_calories

# Lint
flake8 app.py fitness.py models.py tests
```

Each test receives its own temporary SQLite database via the `app` fixture, so the suite is
order-independent and leaves no artefacts behind.

### Coverage areas

| Suite | Focus |
| --- | --- |
| `test_fitness.py` | Calorie factors, BMI and classification, program recommendation, adherence validation, membership states, summary aggregation |
| `test_app.py` | Health probe, login/logout, authentication guards on every API route, client create/update/delete, program generation, progress tracking, workout logging, membership and report endpoints |

---

## 4. Docker

The `Dockerfile` is multi-stage and exposes three targets:

| Stage | Purpose |
| --- | --- |
| `builder` | Installs dependencies into `/opt/venv` — build tooling never reaches the final image |
| `runtime` | Slim production image: Python 3.11-slim, virtualenv only, **non-root user** `aceest` (UID 10001), `HEALTHCHECK`, gunicorn entrypoint |
| `test` | Extends `runtime` with Pytest/flake8 and the test suite for CI quality gates |

```bash
# Production image
docker build -t aceest-fitness:latest .
docker run --rm -p 5000:5000 \
  -e ACEEST_SECRET_KEY="a-long-random-value" \
  -e ACEEST_ADMIN_PASSWORD="ChooseAStrongPassword" \
  aceest-fitness:latest

# Test image — run Pytest inside the container
docker build --target test -t aceest-fitness:test .
docker run --rm aceest-fitness:test pytest -v

# Health probe
curl http://localhost:5000/health
```

Optimisations applied: multi-stage build, `python:3.11-slim` base, `--no-cache-dir` installs,
`.dockerignore` to shrink the build context, dependency layer cached before source copy,
non-root runtime user, and a writable `/data` volume path for the SQLite file.

---

## 5. CI/CD integration logic

### 5.1 GitHub Actions — `.github/workflows/main.yml`

Triggered on **every push, every pull request** and manual dispatch.

```text
push / pull_request
        │
        ├── job: build-and-lint
        │      ├── checkout + setup Python 3.11 (pip cache)
        │      ├── pip install -r requirements-dev.txt
        │      ├── python -m compileall      → syntax / build check
        │      ├── flake8 (fatal errors, then full report)
        │      └── pytest --cov              → unit + integration tests
        │
        └── job: docker-build-and-test  (needs: build-and-lint)
               ├── docker buildx build --target test   (GHA layer cache)
               ├── docker run ... pytest -v            → tests inside the container
               ├── docker buildx build --target runtime
               └── curl /health on the running container → smoke test
```

The second job only starts when linting and tests pass, so a broken commit never reaches image
assembly. The pipeline fails the workflow — and therefore the pull request — on any failing stage.

### 5.2 Jenkins — `Jenkinsfile`

Configured as a **Pipeline → Pipeline script from SCM**, pointing at this repository's `main`
branch, so Jenkins pulls both the source and the pipeline definition from GitHub.

| Stage | Action |
| --- | --- |
| Checkout | `checkout scm` pulls the latest commit from GitHub |
| Build Docker Image | Clean build of the `test` and `runtime` targets, tagged `build-${BUILD_NUMBER}` |
| Quality Gate: Pytest | Runs the suite **inside** the freshly built image; a failure fails the build |
| Quality Gate: Lint | Runs flake8 inside the same image |
| Smoke Test | Starts the runtime container and polls `/health` until it responds |
| Post / always | Removes the temporary build images so the agent stays clean |

**Jenkins job setup**

1. Install the *Git*, *Pipeline* and *Docker* plugins; ensure the agent user can run `docker`.
2. **New Item → Pipeline** → name the job (e.g. `aceest-fitness-build`).
3. Under **Pipeline**, choose *Pipeline script from SCM* → *Git* → repository URL → branch `*/main`
   → Script Path `Jenkinsfile`.
4. Optionally enable *GitHub hook trigger for GITScm polling* (or *Poll SCM* `H/5 * * * *`) so the
   BUILD runs on every push.
5. **Build Now** → the console log ends with `Finished: SUCCESS` when all gates pass.

### 5.3 Division of responsibility

* **GitHub Actions** is the fast feedback loop on every push and pull request (lint, tests, image
  assembly, containerised tests, smoke test).
* **Jenkins** is the controlled BUILD environment and secondary quality gate: it rebuilds the image
  from a clean checkout and re-executes the suite, proving the code integrates outside a developer
  workstation.

---

## 6. Git workflow

The repository follows a conventional-commit style history with one commit per responsibility
(application, tests, Docker, CI, Jenkins, documentation). Suggested branch model:

| Branch | Purpose |
| --- | --- |
| `main` | Always releasable; protected by the CI workflow |
| `feature/*` | New functionality |
| `fix/*` | Defect correction |
| `infra/*` | Docker, Jenkins, GitHub Actions changes |

```bash
git checkout -b feature/workout-logging
git commit -m "feat(workouts): validate workout type and duration"
git push -u origin feature/workout-logging   # opens a PR → CI runs automatically
```

---

## 7. API reference

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness probe (public) |
| `GET/POST` | `/login` | HTML form or JSON login |
| `GET` | `/logout` | Clear the session |
| `GET` | `/dashboard` | Trainer dashboard (authenticated) |
| `GET` | `/api/programs` | Program catalogue |
| `GET/POST` | `/api/clients` | List clients / create-update a client |
| `GET/DELETE` | `/api/clients/<name>` | Client record with computed summary / remove client |
| `POST` | `/api/clients/<name>/program` | Recommend and assign a program |
| `GET/POST` | `/api/clients/<name>/progress` | Weekly adherence entries |
| `GET/POST` | `/api/clients/<name>/workouts` | Workout log |
| `GET` | `/api/clients/<name>/membership` | Membership status |
| `GET` | `/api/clients/<name>/report` | Full JSON report |

All `/api/*` routes return `401 {"error": "Authentication required"}` when unauthenticated and
`400 {"error": "..."}` for validation failures.

---

## 8. Security notes

* Passwords stored as PBKDF2-SHA256 hashes (`werkzeug.security`), never in plain text.
* Every SQL statement is parameterised — no string concatenation of user input.
* Session cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` when `ACEEST_COOKIE_SECURE=1`.
* Server-side validation on all write endpoints (ranges, enums, date formats).
* The dashboard renders API data with `textContent`, avoiding HTML injection.
* The container runs as a non-root user with no build toolchain present.
