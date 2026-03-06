from fastapi.templating import Jinja2Templates

from app.services.image_urls import resolve_image_url

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["resolve_image_url"] = resolve_image_url
