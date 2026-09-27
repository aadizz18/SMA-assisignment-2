from fastapi import FastAPI, Request, Depends, Form, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os

from . import models, database
from .services import crawler, worker

# Create DB tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Website Archive Submitter")

# We will create the static and templates directory later
os.makedirs("app/static", exist_ok=True)
os.makedirs("app/templates", exist_ok=True)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.on_event("startup")
async def startup_event():
    # Start the background worker loop in an asyncio task
    import asyncio
    asyncio.create_task(worker.queue_worker_loop())

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(database.get_db)):
    domains_count = db.query(models.Domain).count()
    urls_count = db.query(models.URLItem).count()
    submitted_count = db.query(models.ArchiveSubmission).filter(models.ArchiveSubmission.status == "Success").count()
    failed_count = db.query(models.ArchiveSubmission).filter(models.ArchiveSubmission.status == "Failed").count()
    queued_count = db.query(models.URLItem).filter(models.URLItem.status == "Queued").count()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "domains_count": domains_count,
        "urls_count": urls_count,
        "submitted_count": submitted_count,
        "failed_count": failed_count,
        "queued_count": queued_count
    })

@app.get("/api/stats")
async def get_stats(db: Session = Depends(database.get_db)):
    from sqlalchemy import func
    # Breakdown of URL statuses
    status_counts = db.query(models.URLItem.status, func.count(models.URLItem.id)).group_by(models.URLItem.status).all()
    status_dict = {s: c for s, c in status_counts}
    
    # Top 5 domains by URL count
    top_domains = db.query(models.Domain.url, func.count(models.URLItem.id))\
                    .join(models.URLItem, models.Domain.id == models.URLItem.domain_id)\
                    .group_by(models.Domain.id)\
                    .order_by(func.count(models.URLItem.id).desc())\
                    .limit(5).all()
                    
    domain_labels = [d[0] for d in top_domains]
    domain_counts = [d[1] for d in top_domains]
    
    return {
        "status_distribution": {
            "labels": ["Queued", "Processing", "Submitted", "Failed"],
            "data": [
                status_dict.get("Queued", 0),
                status_dict.get("Processing", 0),
                status_dict.get("Submitted", 0),
                status_dict.get("Failed", 0)
            ]
        },
        "top_domains": {
            "labels": domain_labels,
            "data": domain_counts
        }
    }

@app.get("/domains", response_class=HTMLResponse)
async def domains_page(request: Request, db: Session = Depends(database.get_db)):
    domains = db.query(models.Domain).order_by(models.Domain.id.desc()).all()
    return templates.TemplateResponse("domains.html", {"request": request, "domains": domains})

@app.post("/domains")
async def add_domain(
    request: Request, 
    url: str = Form(...), 
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(database.get_db)
):
    # Normalize domain
    if not url.startswith("http"):
        url = "https://" + url
        
    domain = db.query(models.Domain).filter(models.Domain.url == url).first()
    if not domain:
        domain = models.Domain(url=url, status="Crawling")
        db.add(domain)
        db.commit()
        db.refresh(domain)
        
        # Start crawl in background
        background_tasks.add_task(crawler.crawl_domain, domain.id)
    else:
        # Re-trigger crawl if already exists
        domain.status = "Crawling"
        db.commit()
        background_tasks.add_task(crawler.crawl_domain, domain.id)
        
    domains = db.query(models.Domain).order_by(models.Domain.id.desc()).all()
    return templates.TemplateResponse("partials/domain_list.html", {"request": request, "domains": domains})

@app.get("/repository", response_class=HTMLResponse)
async def repository_page(request: Request, q: str = "", domain_id: int = 0, db: Session = Depends(database.get_db)):
    query = db.query(models.URLItem)
    if q:
        query = query.filter(models.URLItem.normalized_url.contains(q))
    if domain_id:
        query = query.filter(models.URLItem.domain_id == domain_id)
        
    urls = query.order_by(models.URLItem.id.desc()).limit(100).all()
    domains = db.query(models.Domain).all()
    
    # If HTMX request, return only the rows
    if "hx-request" in request.headers:
        return templates.TemplateResponse("partials/repository_rows.html", {"request": request, "urls": urls})
        
    return templates.TemplateResponse("repository.html", {"request": request, "urls": urls, "domains": domains, "q": q, "domain_id": domain_id})
