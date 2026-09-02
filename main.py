import uvicorn
from src.api.server import app
from config import settings

if __name__ == "__main__":
    print(f"Starting {settings.APP_NAME} v{settings.VERSION}")
    print(f"Dashboard available at http://localhost:8000")
    uvicorn.run("src.api.server:app", host="0.0.0.0", port=8000, reload=False)
