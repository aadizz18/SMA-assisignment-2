import httpx
import logging

async def submit_to_wayback(url: str):
    wayback_submit_url = f"https://web.archive.org/save/{url}"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(wayback_submit_url)
            
            # The Wayback Machine usually redirects to the saved page.
            # Example response URL: https://web.archive.org/web/20231024/http://example.com
            if response.status_code == 200:
                archive_url = str(response.url)
                if "web.archive.org/web/" in archive_url:
                    return {
                        "status": "Success",
                        "archive_url": archive_url,
                        "http_status": response.status_code
                    }
                else:
                    return {
                        "status": "Failed",
                        "error_message": "Unexpected response format from Wayback Machine",
                        "http_status": response.status_code
                    }
            else:
                return {
                    "status": "Failed",
                    "error_message": f"Wayback Machine returned status {response.status_code}",
                    "http_status": response.status_code
                }
    except Exception as e:
        return {
            "status": "Failed",
            "error_message": str(e),
            "http_status": None
        }

async def submit_to_archive_today(url: str):
    # Archive.today requires a POST request with the 'url' form field
    submit_endpoint = "https://archive.is/submit/"
    data = {"url": url}
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.post(submit_endpoint, data=data)
            
            # Usually it redirects to the new archive URL or a processing page
            if response.status_code == 200:
                return {
                    "status": "Success",
                    "archive_url": str(response.url),
                    "http_status": response.status_code
                }
            else:
                 return {
                    "status": "Failed",
                    "error_message": f"Archive.today returned status {response.status_code}",
                    "http_status": response.status_code
                }
    except Exception as e:
        return {
            "status": "Failed",
            "error_message": str(e),
            "http_status": None
        }
