FastAPI best practices and conventions. Use when working with FastAPI APIs and Pydantic models. Write new code or refactor and update old code following these patterns.

## Use the `fastapi` CLI

Run dev server: `fastapi dev` | Production: `fastapi run`

Add entrypoint in `pyproject.toml`:
```toml
[tool.fastapi]
entrypoint = "my_app.main:app"
```

## Use `Annotated`

Always prefer `Annotated` for parameter and dependency declarations:

```python
from typing import Annotated
from fastapi import FastAPI, Path, Query

app = FastAPI()

@app.get("/items/{item_id}")
async def read_item(
    item_id: Annotated[int, Path(ge=1, description="The item ID")],
    q: Annotated[str | None, Query(max_length=50)] = None,
):
    return {"message": "Hello World"}
```

For dependencies, create reusable type aliases:
```python
CurrentUserDep = Annotated[dict, Depends(get_current_user)]

@app.get("/items/")
async def read_item(current_user: CurrentUserDep):
    return {"message": "Hello World"}
```

## Do not use Ellipsis for path operations or Pydantic models

Required parameters don't need `...` as default.

## Return Type or Response Model

Include return types for validation, filtering, docs, and serialization. Use `response_model` when the return type differs from the validation type.

## Pydantic models with `model_config`

Use `model_config = ConfigDict(from_attributes=True)` — NOT `class Config`.

## Use `Form()` for form data, not `Body()`

## async and sync

Use `async def` with `await`. Use plain `def` for blocking code (runs in threadpool). Never run blocking code inside `async` functions. Use `asyncer` (`asyncify`/`syncify`) when mixing.

## Stream JSON Lines

```python
@app.get("/items/stream")
async def stream_items() -> AsyncIterable[Item]:
    for item in items:
        yield item
```

## Stream bytes

Declare `response_class=StreamingResponse` subclass and use `yield`.

## Do not use Pydantic RootModels

Use regular type annotations with `Annotated` and Pydantic validation utilities instead.

## One HTTP operation per function

Don't mix HTTP operations — one function per method.

## Tools: uv, ruff, ty

Use `uv` for deps, `ruff` for lint/format, `ty` for type checking.
