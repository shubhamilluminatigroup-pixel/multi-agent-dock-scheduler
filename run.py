import uvicorn

if __name__ == "__main__":
    print("Starting Multi-Agent ETA Dock & Slot Scheduling System on http://127.0.0.1:8050 ...")
    uvicorn.run("server:app", host="127.0.0.1", port=8050, reload=False)
