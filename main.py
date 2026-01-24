from fastapi import FastAPI
import os

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World", "Server": "Oracle Cloud Free Tier"}

@app.get("/health")
def health_check():
    return {"status": "ok"}
