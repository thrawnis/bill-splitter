from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .routes import auth, dashboard, groups, bills, profile

app = FastAPI(title="BillSplit")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(groups.router)
app.include_router(bills.router)
app.include_router(profile.router)


@app.get("/")
async def root():
    return RedirectResponse("/dashboard", status_code=302)


@app.exception_handler(307)
async def temp_redirect_handler(request: Request, exc):
    location = exc.headers.get("Location", "/auth/login")
    return RedirectResponse(url=location, status_code=302)
