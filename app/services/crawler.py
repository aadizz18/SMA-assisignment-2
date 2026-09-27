import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urldefrag
from sqlalchemy.orm import Session
from .. import models, database
import time

async def get_html_links(url: str, html: str):
    soup = BeautifulSoup(html, 'html.parser')
    links = set()
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if not href:
            continue
        # normalize
        absolute_url = urljoin(url, href)
        # remove fragments
        absolute_url, _ = urldefrag(absolute_url)
        if absolute_url.startswith('http'):
            links.add(absolute_url)
    return list(links)

async def crawl_worker(name, queue, visited, domain_id, domain_name, client, db_session):
    while True:
        try:
            current_url = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
            
        if len(visited) >= 5000: # Increased limit for advanced crawling
            queue.task_done()
            continue

        try:
            response = await client.get(current_url)
            if response.status_code == 200 and 'text/html' in response.headers.get('Content-Type', ''):
                links = await get_html_links(current_url, response.text)
                
                # Bulk insert new links to DB
                new_urls = []
                for link in links:
                    parsed_link = urlparse(link)
                    if parsed_link.netloc == domain_name and link not in visited:
                        visited.add(link)
                        queue.put_nowait(link)
                        
                        # Add to DB bulk array
                        url_item = models.URLItem(
                            domain_id=domain_id,
                            original_url=link,
                            normalized_url=link,
                            discovery_source="Crawler"
                        )
                        new_urls.append(url_item)
                
                if new_urls:
                    # Optimized bulk insertion
                    db_session.add_all(new_urls)
                    db_session.commit()
                    
        except Exception as e:
            print(f"[{name}] Error crawling {current_url}: {e}")
            
        queue.task_done()
        await asyncio.sleep(0.1) # small throttle to not kill the target server

async def crawl_domain(domain_id: int):
    # Advanced Concurrent Crawler using asyncio.Queue
    db = database.SessionLocal()
    try:
        domain = db.query(models.Domain).filter(models.Domain.id == domain_id).first()
        if not domain:
            return
            
        domain.status = "Crawling"
        db.commit()
        
        base_url = domain.url
        parsed_base = urlparse(base_url)
        domain_name = parsed_base.netloc
        
        # Make sure base URL is in DB
        url_item = db.query(models.URLItem).filter(models.URLItem.normalized_url == base_url).first()
        if not url_item:
            db.add(models.URLItem(domain_id=domain_id, original_url=base_url, normalized_url=base_url, discovery_source="Seed"))
            db.commit()

        visited = {base_url}
        queue = asyncio.Queue()
        queue.put_nowait(base_url)
        
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, limits=httpx.Limits(max_connections=50)) as client:
            # Spawn 10 concurrent workers
            workers = [
                asyncio.create_task(crawl_worker(f"worker-{i}", queue, visited, domain_id, domain_name, client, db))
                for i in range(10)
            ]
            
            # Wait until queue is fully processed
            await queue.join()
            
            # Cancel workers
            for w in workers:
                w.cancel()
                
        domain.status = "Completed"
        db.commit()
    except Exception as e:
        print(f"Crawl domain error: {e}")
        domain.status = "Failed"
        db.commit()
    finally:
        db.close()
