import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import init_db, SessionLocal, Site, Item
from scraper import fetch_rss, fetch_static, fetch_dynamic, debug_fetch, debug_fetch_dynamic


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)

FRONTEND_DIR = Path("/app/frontend")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class SiteCreate(BaseModel):
    name: str
    url: str
    type: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


# --- Sites ---

@app.post("/sites")
def create_site(body: SiteCreate, db: Session = Depends(get_db)):
    site = Site(name=body.name, url=body.url, type=body.type)
    db.add(site)
    db.commit()
    db.refresh(site)
    return {"id": site.id, "name": site.name, "url": site.url, "type": site.type}


@app.get("/sites")
def list_sites(db: Session = Depends(get_db)):
    sites = db.query(Site).order_by(Site.created_at.desc()).all()
    return [
        {"id": s.id, "name": s.name, "url": s.url, "type": s.type}
        for s in sites
    ]


@app.delete("/sites/{site_id}")
def delete_site(site_id: int, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    db.query(Item).filter(Item.site_id == site_id).delete()
    db.delete(site)
    db.commit()
    return {"ok": True}


@app.post("/sites/{site_id}/fetch")
async def fetch_site(site_id: int, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    if site.type == "dynamic":
        try:
            entries = await asyncio.wait_for(fetch_dynamic(site.url), timeout=60)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Dynamic fetch timed out")
    elif site.type == "static":
        entries = fetch_static(site.url)
    else:
        entries = fetch_rss(site.url)

    existing_urls = set(
        r[0] for r in db.query(Item.url).filter(Item.site_id == site_id).all()
    )

    added = 0
    for entry in entries:
        if entry["url"] in existing_urls:
            continue
        item = Item(
            site_id=site_id,
            title=entry["title"],
            url=entry["url"],
            summary=entry["summary"],
            published=entry.get("published", ""),
            image=entry.get("image", ""),
        )
        db.add(item)
        added += 1

    db.commit()
    return {"fetched": len(entries), "added": added}


# --- Items ---

@app.get("/items")
def list_items(site_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Item).order_by(Item.created_at.desc())
    if site_id is not None:
        query = query.filter(Item.site_id == site_id)
    items = query.all()
    return [
        {
            "id": i.id,
            "site_id": i.site_id,
            "title": i.title,
            "url": i.url,
            "summary": i.summary,
            "published": i.published,
            "image": i.image,
            "is_read": i.is_read,
        }
        for i in items
    ]


@app.get("/debug")
def debug(url: str):
    return debug_fetch(url)


@app.get("/debug-dynamic")
async def debug_dynamic(url: str):
    try:
        return await asyncio.wait_for(debug_fetch_dynamic(url), timeout=60)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Dynamic debug timed out")


@app.patch("/items/{item_id}/read")
def mark_read(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.is_read = True
    db.commit()
    return {"ok": True}
