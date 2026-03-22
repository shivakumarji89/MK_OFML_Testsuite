from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
from modules.snapper.routes import router as snapper_router

app = FastAPI(title="OFML Testsuite")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(snapper_router)

@app.get("/")
def home():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)
