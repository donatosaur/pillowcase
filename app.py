# Author:      Donato Quartuccia
# Modified:    2022-02-23
# Description: App configuration

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import get_env

from routes import image_router


# create and serve app
app = FastAPI(
    title="Pillowcase",
    description="A simple API that wraps Pillowcase for Resize and Rotate requests via HTTP",
    contact={
        "name": "Donato Quartuccia",
        "url": "https://github.com/donatosaur",
    },
    license_info={
      "name": "Apache License, Version 2.0",
      "url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    # docs_url=None,
    # redoc_url=None,
)

# set CORS to allow requests for anything on the same host
app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://{get_env().HOST}", f"http://{get_env().HOST}:P{get_env().PORT}"],
    allow_methods=["GET", "POST"],
    allow_headers=['*'],
)

# attach routes
app.include_router(image_router)


# start uvicorn; see docs at https://www.uvicorn.org/#command-line-options for other options
if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=get_env().HOST,
        port=get_env().PORT,
        reload=get_env().DEBUG,
    )
