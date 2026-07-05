from fastapi import FastAPI

from app.api.v1.groups import router as groups_router
from app.api.v1.task_group import group_tasks_router, router as task_group_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.user_group import router as user_group_router
from app.api.v1.users import router as users_router

app = FastAPI(title="TaskNest", version="1.0.0")

app.include_router(users_router)
app.include_router(groups_router)
app.include_router(user_group_router)
app.include_router(tasks_router)
app.include_router(task_group_router)
app.include_router(group_tasks_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
