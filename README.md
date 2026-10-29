# Event Ticketing & Seat Reservation API

Ticket HS-2026-0872 (Halcyon Systems). A Django REST Framework microservice for
venues, events, seats and seat reservations, with JWT authentication,
role-based permissions, a PostgreSQL database, Docker packaging and a GitHub
Actions CI pipeline.

## Features

- Django 6 + Django REST Framework, JWT auth (`djangorestframework-simplejwt`)
- Roles: **admin** (`is_staff`) manages venues, seats and events; **standard
  users** browse published events and manage only their own reservations
- Double-booking is prevented at the database level (unique constraint) and
  validated in the API for friendly errors
- Standardised JSON error schema for every error
- `/health/` endpoint (database connectivity, uptime, service status)
- Swagger / OpenAPI docs via `drf-spectacular`
- Multi-stage Dockerfile, `docker-compose.yml` with PostgreSQL
- CI: lint, tests against a temporary PostgreSQL database, Docker build

## Quick start (Docker)

Requires Docker with Compose.

```bash
docker compose up --build
```

The API is then available at http://localhost:8000. The app waits for
PostgreSQL to be healthy and runs migrations on start.

Create an admin user (in a second terminal):

```bash
docker compose exec -e DJANGO_SECRET_KEY=unused web python manage.py createsuperuser
```

Stop everything with `docker compose down` (add `-v` to also delete the
database volume).

| URL | What |
|---|---|
| http://localhost:8000/api/docs/ | Swagger UI |
| http://localhost:8000/api/schema/ | OpenAPI schema |
| http://localhost:8000/health/ | Health check |
| http://localhost:8000/admin/ | Django admin |

## Local development (without Docker)

Without `POSTGRES_HOST` set, the app falls back to SQLite.

```bash
python -m venv venv
source venv/bin/activate          # Windows Git Bash: source venv/Scripts/activate
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py runserver
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | insecure dev key | Set a real secret in production |
| `DJANGO_DEBUG` | `True` | `False` in Docker/CI |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated |
| `POSTGRES_HOST` | unset (SQLite) | Setting it switches to PostgreSQL |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_PORT` | `ticketing` / `ticketing` / `ticketing` / `5432` | Database connection |

## API overview

| Endpoint | Methods | Access |
|---|---|---|
| `/api/auth/register/` | POST | Public |
| `/api/auth/token/` | POST | Public (returns access + refresh tokens) |
| `/api/auth/token/refresh/` | POST | Public |
| `/api/auth/me/` | GET | Authenticated |
| `/api/venues/` | GET, POST, PUT, PATCH, DELETE | Read: any user. Write: admin |
| `/api/seats/` (`?venue=<id>`) | GET, POST, PUT, PATCH, DELETE | Read: any user. Write: admin |
| `/api/events/` (`?venue=<id>`) | GET, POST, PUT, PATCH, DELETE | Read: any user (unpublished hidden from non-admins). Write: admin |
| `/api/reservations/` | GET, POST, DELETE | Users see/manage their own; admins see all |
| `/api/reservations/{id}/cancel/` | POST | Owner or admin; frees the seats |
| `/health/` | GET | Public |

Reservations cannot be edited. Cancel and rebook instead.

## Sample cURL commands

Register and log in:

```bash
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"AlicePass12345"}'

curl -X POST http://localhost:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"AlicePass12345"}'
```

Copy the `access` value from the response and use it as the bearer token:

```bash
TOKEN="paste-access-token-here"
curl http://localhost:8000/api/auth/me/ -H "Authorization: Bearer $TOKEN"
```

As an admin, create a venue, seats and an event:

```bash
curl -X POST http://localhost:8000/api/venues/ \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Moses Mabhida Stadium","address":"Isaiah Ntshangase Rd","city":"Durban"}'

curl -X POST http://localhost:8000/api/seats/ \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"venue":1,"section":"A","row":"1","number":1}'

curl -X POST http://localhost:8000/api/events/ \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"venue":1,"title":"Summer Concert","starts_at":"2026-12-15T18:00:00Z","ends_at":"2026-12-15T22:00:00Z","ticket_price":"150.00"}'
```

As a standard user, book and cancel seats:

```bash
curl -X POST http://localhost:8000/api/reservations/ \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"event":1,"seat_ids":[1]}'

curl -X POST http://localhost:8000/api/reservations/1/cancel/ \
  -H "Authorization: Bearer $TOKEN"
```

Health check:

```bash
curl http://localhost:8000/health/
```

## Error format

Every error uses the same JSON shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Validation failed.",
    "details": {"seat_ids": ["Seats already reserved: [2]"]},
    "status": 400
  }
}
```

Codes: `validation_error` (400), `authentication_failed` (401),
`permission_denied` (403), `not_found` (404), `method_not_allowed` (405),
`conflict` (409, deleting a record other records depend on),
`server_error` (500).

## Tests

```bash
python -m pytest --cov --cov-report=term-missing
```

83 tests cover models, authentication, permissions, validation, booking,
double-booking, cancellation, the error schema and the health endpoint.
Coverage is about 98%, and CI fails below 80%.

## CI pipeline

`.github/workflows/ci.yml` runs three jobs in order:

1. **Lint**: `black --check` and `flake8`
2. **Test**: starts a temporary PostgreSQL service, checks for missing
   migrations, runs pytest with an 80% coverage floor
3. **Build Docker image**: builds the image after tests pass

## Database index choices

PostgreSQL does not automatically index the referencing side of a foreign key,
so Django's automatic FK indexes cover the single-column lookups, and the
indexes below are added for the queries this API actually runs.

| Index | Why |
|---|---|
| `Venue.city` (`db_index`) | Venues are filtered and grouped by city, and city values repeat a lot. |
| `Event (venue, starts_at)` | Powers "events at this venue, in date order", which is the `?venue=` filter combined with the default `starts_at` ordering. One composite index serves both the filter and the sort. |
| `Event (is_published, starts_at)` | Standard users only ever see published events, so every non-admin list query filters on `is_published` and sorts by date. |
| `Reservation (user, status)` | The "my reservations" query filters by the current user, and the status column supports filtering confirmed vs cancelled. |
| `Reservation (event, status)` | Lets an admin or report count active reservations for an event without scanning every reservation. |
| `unique_seat_per_event` on `ReservationSeat (event, seat)` | The core business rule: a seat can be held once per event. The unique constraint creates an index, so the availability check ("which of these seats are taken for this event?") is an index lookup, and the database itself blocks double booking even under concurrent requests. |
| `unique_seat_per_venue` on `Seat (venue, section, row, number)` | Prevents duplicate seats in a venue, and speeds up seat lookups and the `?venue=` filter. |
| `unique_seat_per_reservation` on `ReservationSeat (reservation, seat)` | Stops the same seat being listed twice in one reservation, and speeds up loading a reservation's seats. |

Composite indexes put the equality column first and the sort or range column
second, so one index serves both the filter and the ordering.

## Design notes

- The `event` column is stored on the `ReservationSeat` join table as well as
  on `Reservation`, so the unique `(event, seat)` constraint can live in the
  database. The join model copies it from the reservation on save.
- Total price is calculated on the server, and clients cannot set it.
- Booking runs in a transaction, and a conflict that slips past validation (two
  simultaneous requests) is caught and returned as a clean `400`.
- Deleting a venue, event or seat that other records depend on returns `409`
  rather than failing with a server error.
