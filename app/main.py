from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from .routes import auth, bills, dashboard, groups, profile

app = FastAPI(title="BillSplit", docs_url=None, redoc_url=None, openapi_url=None)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(groups.router)
app.include_router(bills.router)
app.include_router(profile.router)


@app.get("/")
async def root():
    return RedirectResponse("/dashboard", status_code=302)


@app.exception_handler(307)
async def auth_redirect_handler(request: Request, exc):
    return RedirectResponse(url=exc.headers.get("Location", "/auth/login"), status_code=302)
