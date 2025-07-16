# Controller Service

The Controller manages service deployment and optimises the
agent-to-service allocation.

## Key Components

- **`controller.py`** – FastAPI application exposing HTTP endpoints.
- **`domain/`** – domain models such as `ServiceInstance`.
- **`application/`** – functional logic (`optimizer_service.py`).
- **`optimizer.py`** – compatibility wrapper exposing the original functions
  `optimize`, `uniform` and `most_remaining`.

The refactoring separates business rules from infrastructure code while keeping
all APIs intact.
