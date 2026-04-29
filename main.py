from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
from modules.snapper.routes import router as snapper_router
from modules.search.routes import router as search_router

app = FastAPI(title="OFML Testsuite")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(snapper_router)
app.include_router(search_router)

@app.get("/")
def home():
    return FileResponse("static/index.html")

@app.get("/snapper/")
def snapper():
    return FileResponse("static/snapper/index.html")

@app.get("/search/")
def search_page():
    return FileResponse("static/search/index.html")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8090, reload=False)
