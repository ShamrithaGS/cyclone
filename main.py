from fastapi import FastAPI, Query

from advisory_service import build_advisory_response

app = FastAPI(title="Cyclone Advisory API")


@app.get("/advisory")
def advisory(cyclone_id: str = Query(default="demo")):
    return build_advisory_response(cyclone_id)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
