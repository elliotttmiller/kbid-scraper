#!/usr/bin/env python3
import uvicorn


if __name__ == "__main__":
    uvicorn.run("auction_engine.api:app", host="127.0.0.1", port=8000, reload=False)
