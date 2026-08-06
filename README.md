# Smart Fridge Assistant - Backend API

Backend REST API for the Smart Fridge Assistant application built with Django, Django REST Framework (DRF), Celery, Redis, and Google Gemini AI.

---

## 🛠️ Tech Stack & Dependencies

* **Core Framework:** Django 6.0 & Django REST Framework (DRF 3.17)
* **Database:** PostgreSQL (`psycopg2-binary`)
* **Authentication:** SimpleJWT (`djangorestframework_simplejwt` & `PyJWT`)
* **API Documentation:** `drf-spectacular` (OpenAPI 3.0 & Swagger UI)
* **Asynchronous Tasks:** Celery 5.6 & Redis 8.0
* **AI Integration:** Google GenAI SDK (`google-genai` 1.28)
* **Filtering & Utilities:** `django-filter`, `python-dotenv`, `django-cors-headers`
* **Code Quality & Testing:** `ruff`, `pytest`, `pytest-django`

---

## 🚀 Getting Started

### Prerequisites

* Python 3.10+
* PostgreSQL database
* Redis server (for Celery broker and cache)
* Docker & Docker Compose (optional)

### Local Setup (Without Docker)

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd smart-fridge-backend

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
4. **Configure environment variables:**
   Copy .env.sample to .env and fill in the required parameters:
   ```bash
   cp .env.sample .env
5. **Run database migrations:**
   ```bash
   python manage.py migrate
6. **Start the development server:**
   ```bash
   python manage.py runserver

## ⚡ Running Background Workers (Celery & Redis)
Ensure Redis is running locally, then start the Celery worker process in a separate terminal:
   ```bash
      celery -A core worker --loglevel=info
   ```

## 🐳 Running with Docker
To spin up the full backend stack (Django API, PostgreSQL, Redis, and Celery) using Docker Compose:
   ```bash
      docker-compose up --build
   ```

## 🔑 Environment Variables
The application relies on the following environment variables (defined in .env / .env.sample):
    
| Variable | Description |
| --- | --- |
| `SECRET_KEY` | Django secret key |
| `DEBUG` | Enable or disable debug mode (`True` / `False`) |
| `ALLOWED_HOSTS` | Comma-separated list of allowed host headers |
| `DB_NAME` | PostgreSQL database name |
| `DB_USER` | PostgreSQL database user |
| `DB_PASSWORD` | PostgreSQL database password |
| `DB_HOST` | PostgreSQL host address |
| `DB_PORT` | PostgreSQL port |
| `GEMINI_API_KEY` | API key for Google Gemini AI integration |
| `GEMINI_MODEL` | Gemini model to use (e.g. `gemini-3.1-flash-lite`) |
| `REDIS_URL` | Redis connection URL |
| `CELERY_BROKER_URL` | Celery broker URL (typically points to Redis) |
| `CORS_ALLOWED_ORIGINS` | Comma-separated list of frontend origins allowed to call this API (defaults to `http://localhost:4200`) |

---

## 📚 API Endpoints Summary

Interactive API documentation and schema testing are available via Swagger UI at /api/docs/.

### 🔑 Authentication (`/api/auth/`)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/auth/login/` | Authenticate user and return JWT access/refresh tokens |
| `POST` | `/api/auth/register/` | Register a new user account |
| `GET` | `/api/auth/me/` | Fetch profile details of the currently authenticated user |
| `GET` | `/api/auth/protected-test/` | Verification endpoint for checking JWT token validity |
| `POST` | `/api/auth/token/refresh/` | Refresh an expired access JWT token |

---

### 🩺 Health (`/api/health/`)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health/` | Operational status check |

---

### 🥦 Products / Fridge (`/api/products/`)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/products/` | Retrieve list of available products/fridge items |
| `POST` | `/api/products/` | Add a new product to the fridge |
| `GET` | `/api/products/{id}/` | Retrieve details of a specific product |
| `PUT` | `/api/products/{id}/` | Full update of a product |
| `PATCH` | `/api/products/{id}/` | Partial update of a product |
| `DELETE` | `/api/products/{id}/` | Remove a product |

---

### 🍳 Recipes (`/api/recipes/`)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/recipes/generate/` | Trigger AI recipe generation based on fridge contents |
| `POST` | `/api/recipes/save/` | Save a generated recipe to the user's collection |
| `GET` | `/api/recipes/saved/` | List all saved user recipes |
| `DELETE` | `/api/recipes/saved/{id}/` | Remove a saved recipe |
| `POST` | `/api/recipes/suggestions/` | Request asynchronous recipe suggestions |
| `GET` | `/api/recipes/suggestions/{task_id}/` | Check the status or result of an async recipe generation task |

---

## 🤖 AI Recipe Generation — Detailed Guide

This section documents the AI recipe generation flow in detail, for developers integrating against it and for evaluators reviewing the implementation.

### Overview

The typical flow is: **generate → save → get → delete**.

1. Call `POST /api/recipes/generate/` to get AI-generated recipe suggestions based on the user's current fridge contents.
2. Optionally call `POST /api/recipes/save/` with the `id` of a recipe from the generate response, to bookmark it.
3. Call `GET /api/recipes/saved/` to list bookmarked recipes.
4. Call `DELETE /api/recipes/saved/{id}/` to remove a bookmark.

### Gemini API setup

1. Get a free API key from [Google AI Studio](https://aistudio.google.com/apikey).
2. Set it in your `.env` file:
   ```
   GEMINI_API_KEY=your-key-here
   GEMINI_MODEL=gemini-3.1-flash-lite
   ```
   `gemini-3.1-flash-lite` is recommended for local development — it currently has the highest free-tier rate limit among Gemini models. `gemini-flash-latest` is also supported and always points to the current recommended stable model, but has a lower free-tier quota.
3. Restart the containers (or the dev server) after changing `.env` so the new key is picked up:
   ```bash
   docker-compose down && docker-compose up --build
   ```
4. Google's free tier enforces its own requests-per-minute and requests-per-day limits, independent of this API's own daily limit described below. If you see `503` errors under heavy local testing, this is usually Google's free tier being temporarily overloaded — the backend automatically retries with an increasing delay before giving up.

### `POST /api/recipes/generate/`

Fetches the authenticated user's current fridge contents, generates recipe suggestions via Gemini, and — unlike `/api/recipes/suggestions/` — waits for the result and returns it synchronously (up to 60 seconds), instead of requiring the client to poll a task status endpoint. Each generated recipe is also saved to the database, and its `id` is included in the response so it can immediately be passed to `/api/recipes/save/`.

**Request:** no body required. Requires `Authorization: Bearer <access_token>`.

**Example response — `200 OK`:**
```json
{
  "recipes": [
    {
      "id": 42,
      "title": "Classic Fluffy Scrambled Eggs",
      "ingredients": ["eggs", "butter", "salt", "black pepper"],
      "steps": [
        "Crack the eggs into a bowl and whisk until combined.",
        "Melt butter in a non-stick skillet over medium-low heat.",
        "Pour in the eggs and gently stir until softly set.",
        "Season with salt and pepper, and serve immediately."
      ]
    }
  ]
}
```

#### Daily limit behavior

This endpoint enforces a **daily limit of 5 requests per user**, separate from Gemini's own free-tier quota, to keep API usage predictable across the team while testing.

* The counter is tracked per user, per calendar day, in Redis, and resets automatically at midnight.
* On the 6th request of the day, the endpoint returns `429 Too Many Requests`:
  ```json
  {
    "detail": "Daily request limit reached (5 per day). Please try again tomorrow."
  }
  ```
* If Gemini itself is unavailable (after automatic retries) or the request times out, the endpoint returns `503 Service Unavailable`:
  ```json
  {
    "detail": "Recipe generation service is currently unavailable. Please try again later."
  }
  ```

### `POST /api/recipes/save/`

Saves an existing recipe (by `id`, typically one just returned by `/generate/`) to the authenticated user's favourites.

**Request:**
```json
{
  "recipe_id": 42
}
```

**Response — `201 Created`:**
```json
{
  "id": 5,
  "user_id": 2,
  "recipe_id": 42
}
```

Other responses: `400 Bad Request` if this recipe is already saved by the user; `404 Not Found` if `recipe_id` doesn't exist.

### `GET /api/recipes/saved/`

Returns all recipes saved by the authenticated user, with full details.

**Response — `200 OK`:**
```json
[
  {
    "id": 42,
    "title": "Classic Fluffy Scrambled Eggs",
    "ingredients": ["eggs", "butter", "salt", "black pepper"],
    "steps": ["Crack the eggs into a bowl and whisk until combined.", "..."],
    "created_at": "2026-07-21T21:13:10.488260Z"
  }
]
```

Returns an empty array `[]` if the user has no saved recipes.

### `DELETE /api/recipes/saved/{id}/`

Removes a saved recipe (unbookmarks it). `{id}` is the *saved recipe's* id (from the `id` field returned by `/save/` or `/saved/`).

**Response:** `204 No Content` on success. `404 Not Found` if the saved recipe doesn't exist, or belongs to a different user (both cases return an identical 404, so a client can't distinguish "not found" from "not yours").

---

## 🌐 Frontend Integration

If you're building a separate frontend app (e.g. Angular) that consumes this API:

* **Swagger UI:** once the backend is running, browse all endpoints and try them out at `http://localhost:8000/api/docs/`
* **CORS:** requests from `http://localhost:4200` (Angular's default dev server port) are allowed out of the box. To allow a different origin, set `CORS_ALLOWED_ORIGINS` in your `.env` (comma-separated for multiple origins)
* **Postman collection:** an exported collection with example requests for every endpoint is available — ask a backend team member for the latest export
* **Authentication:** obtain a JWT via `POST /api/auth/login/`, then send it on subsequent requests as `Authorization: Bearer <access_token>`