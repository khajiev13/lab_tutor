## Plan: Refactor to Modular Onion Architecture

We will restructure the backend into a highly organized **Modular Onion Architecture**, grouping code by domain features and separating concerns into strict layers. We will also reorganize tests to mirror this structure.

### Proposed Structure
```text
backend/
├── app/
│   ├── modules/                 # Feature Modules
│   │   ├── courses/
│   │   │   ├── router.py        # API Layer (Controllers)
│   │   │   ├── service.py       # Business Logic Layer
│   │   │   ├── repository.py    # Data Access Layer
│   │   │   ├── models.py        # Domain Entities
│   │   │   ├── schemas.py       # DTOs / Pydantic Models
│   │   │   └── dependencies.py  # Module-specific DI
│   │   └── ...
│   ├── providers/               # Infrastructure / External Services
│   │   └── storage.py           # (was blob_service.py)
│   ├── core/                    # Global Core Components
│   │   ├── database.py
│   │   ├── settings.py
│   │   └── exceptions.py
│   └── main.py
└── tests/
    └── modules/
        └── courses/
            ├── test_router.py
            ├── test_service.py
            └── test_repository.py
```

### Steps
1. **Scaffold Modular Structure**: Create `modules/courses` and `tests/modules/courses` directories.
2. **Migrate Domain Layer**: Move `Course` and `Enrollment` models to `modules/courses/models.py` and schemas to `modules/courses/schemas.py`.
3. **Implement Repository Layer**: Create `modules/courses/repository.py` to encapsulate all SQLAlchemy queries, removing direct DB access from routes.
4. **Implement Service Layer**: Create `modules/courses/service.py` to handle business rules (e.g., "student cannot join twice"), depending only on the Repository.
5. **Implement API Layer**: Create `modules/courses/router.py` to handle HTTP requests, injecting `CourseService` via `dependencies.py`.
6. **Migrate Infrastructure**: Move `services/blob_service.py` to `providers/storage.py` to separate external integrations from domain logic.
7. **Reorganize Tests**: Split `tests/test_courses.py` into granular tests within `tests/modules/courses/` (unit tests for service/repo, integration tests for router).
8. **Update Entry Point**: Refactor `main.py` to register the new modular routers.

### Further Considerations
1. **Shared Models**: How to handle relationships between `User` (in `auth` module) and `Course`? *Recommendation: Use string-based relationships in SQLAlchemy (e.g., `relationship("User")`) to avoid circular imports.*
2. **Testing Strategy**: Should we use a separate DB for tests? *Recommendation: Continue using the existing `conftest.py` fixture approach but adapt it to the new structure.*
