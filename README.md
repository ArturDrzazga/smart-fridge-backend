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
* **Filtering & Utilities:** `django-filter`, `python-dotenv`
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
| `REDIS_URL` | Redis connection URL |
| `CELERY_BROKER_URL` | Celery broker URL (typically points to Redis) |

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