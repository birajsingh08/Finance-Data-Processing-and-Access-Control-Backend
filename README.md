# Finance Data Processing and Access Control Backend

A compact FastAPI backend for managing financial records, dashboard summaries, and role-based access control.

## What It Covers

- User management with active/inactive status
- Role-based permissions for `viewer`, `analyst`, and `admin`
- Financial record CRUD with filtering and soft delete
- Dashboard summary API with totals, category rollups, and monthly trends
- Input validation and clear HTTP error responses
- SQLite persistence for local development

## Assumptions

- Authentication is mock-based. Clients send `X-User-Id` to identify the current user.
- Only active users can access the API.
- `viewer` can read only their profile.
- `analyst` can read records and dashboard summaries.
- `admin` can manage users and financial records.
- Records are soft-deleted so historical data is preserved.

## Local Setup

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the API:

```bash
uvicorn app.main:app --reload
```

The app uses `finance.db` in the project root.

Open `http://127.0.0.1:8000/` for a simple status response, `http://127.0.0.1:8000/health` for a health check, and `http://127.0.0.1:8000/docs` for Swagger UI.

## Run Tests

```bash
python -m unittest discover -s tests
```

## Seeded Users

On first startup the app creates these users:

- `admin@example.com` with role `admin`
- `analyst@example.com` with role `analyst`
- `viewer@example.com` with role `viewer`

Use their generated database IDs in the `X-User-Id` header.

## API Overview

### Health

- `GET /`
- `GET /health`

### Users

- `POST /users` admin only
- `GET /users` admin only
- `GET /users/me` any active user
- `PATCH /users/{user_id}` admin only

### Records

- `POST /records` admin only
- `GET /records` analyst and admin
- `GET /records/{record_id}` analyst and admin
- `PATCH /records/{record_id}` admin only
- `DELETE /records/{record_id}` admin only

### Dashboard

- `GET /dashboard/summary` analyst and admin

## Example Request

```bash
curl -H "X-User-Id: 1" http://127.0.0.1:8000/dashboard/summary
```

## Review Notes

- Authentication is intentionally mock-based so the assignment stays focused on backend design and access control.
- The API uses SQLite for persistence and seeds sample users and records on first startup.
- The test suite covers role enforcement, CRUD behavior, filtering, soft delete, and summary aggregation.

## Design Notes

- The code is organized into models, schemas, security, CRUD, and API wiring.
- Validation is handled at the schema layer with Pydantic.
- Authorization is enforced with role-based dependencies.
- Summary data is computed server-side so a dashboard can consume one compact response.
