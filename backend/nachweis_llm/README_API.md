# FastAPI integration contract

The LLM package does not create the main FastAPI app. Mount its router in the host API:

```python
from fastapi import FastAPI
from nachweis_llm.api import build_router
from nachweis_llm.factory import create_services

app = FastAPI(title="Nachweis API")
llm_services = create_services()
app.include_router(build_router(llm_services))
```

Routes supplied by the package:

- `POST /api/llm/extract`: source-grounded field extraction and follow-up gaps.
- `POST /api/llm/review`: separate second pass on configured critical fields only. The host can dispatch it in the background.
- `POST /api/llm/draft`: deterministic draft text from source-backed or user-locked fields.
- `POST /api/llm/completeness`: formal field-presence checklist; not legal review.
- `POST /api/llm/photos/classify`: fixed-category photo classification.

The host API must add authentication, project-level authorization, event persistence, document versioning,
user-edit locks, status transitions, approval UI, Word/PDF rendering and any send/hand-off action.
The starter routes are intentionally thin and suitable for replacement with host-specific dependencies.
