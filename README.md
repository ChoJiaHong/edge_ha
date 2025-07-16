# Edge HA

This repository manages the high availability components for the Edge system.

## Module Layout

The `Controller` service has been refactored following a Domain Driven Design
approach:

- `Controller/domain` – contains core domain models such as
  `ServiceInstance` representing an inference service instance.
- `Controller/application` – application logic. `optimizer_service.py`
  implements the optimisation algorithm using pure functions and immutable
  dataclasses.
- `Controller/optimizer.py` – compatibility layer exposing the original API
  while delegating to the application layer.

## Deploying

Install dependencies for the controller:

```bash
pip install -r Controller/requirements.txt
```

Run the controller as before. No API changes were introduced, so existing
microservices can interact with it without modification.
