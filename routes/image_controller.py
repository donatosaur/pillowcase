# Author:      Donato Quartuccia
# Modified:    2022-02-25
# Description: Image controller

import uuid
import glob
from typing import Final
from io import BytesIO

from fastapi import APIRouter, HTTPException, Depends, Path, Body, Query, UploadFile
from fastapi.responses import FileResponse, Response
from starlette import status

import PIL
from PIL.Image import (
    Image,
    open as image_from_bytestream  # should only be used on bytestream from request; otherwise use PILOpen
)

from .image_model import ImageModel, PILOpen, ImageError
from config import get_env


# create router; the tags metadata is for FastAPI's doc generator (turned off for now to meet specs)
router = APIRouter(prefix="/image", tags=["image"])


# ------------------------------------------------- Constants --------------------------------------------------

ROTATION_DIRECTION: Final = "'R' for right/clockwise (default), 'L' for left/counterclockwise"
ROTATION_AMOUNT: Final = "A multiple of 90 degrees"
LOCK_ASPECT_RATIO: Final = "True to lock the aspect ratio (default). False to leave it unlocked. " \
                           "Note that leaving it unlocked may result in a stretched image."


# ------------------------------------------------- Helpers --------------------------------------------------
# Capitalization for ImageResponse here is intentional. FastAPI's responses are all callable classes. Ideally,
# this would be as well, but in the interest of time a function works fine.
def ImageResponse(image: Image) -> Response:
    """
    Helper for sending PIL image file responses
    :param image: the PIL image file to send
    """
    # the implementation of PIL.Image.tobytes() doesn't work correctly for compressed image formats like PNG; instead,
    # the Pillow documentation suggests writing to a file-like object (or buffer) instead; in this case, a buffer
    # should work fine (see https://pillow.readthedocs.io/en/stable/reference/Image.html?highlight=tobytes())
    buffer = BytesIO()
    try:
        image.save(buffer, format="png")
        return Response(buffer.getvalue(), media_type="image/png")
    finally:
        buffer.close()


# -------------------------------------------------- CREATE --------------------------------------------------

@router.post("/", response_description="Upload an image", response_model=ImageModel)
async def post_image(
    image_file: UploadFile,
    env=Depends(get_env),
):
    """
    Handles /image POST requests with a file. The request must contain an image with a supported MIME type (see
    https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types and the linked IANA page)
    """
    image_directory = env.IMAGE_DIRECTORY

    # validate the request
    if not image_file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing file")
    elif not image_file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Invalid content type")

    # read the bytestream from the request and attempt to open it as an image
    try:
        with image_from_bytestream(image_file.file) as image_file:
            # create a random and unique id for the file and store it
            image_id = uuid.uuid4()

            while glob.glob(f"{image_directory}/{image_id}*"):
                # pretty unlikely, but possible
                image_id = uuid.uuid4()
            image_file.save(f"{image_directory}/{image_id}.png", "png")
            # return the string representation of the image UUID (in hex)
            return {"image_id": str(image_id)}
    except PIL.UnidentifiedImageError:
        # PIL couldn't determine the correct type of file (it's an unsupported type)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")
    except PIL.Image.DecompressionBombWarning:
        # see the discussion on decompression: https://pillow.readthedocs.io/en/stable/reference/Image.html#functions
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum file size exceeded: {PIL.Image.MAX_IMAGE_PIXELS} pixels"
        )
    finally:
        await image_file.close()


# ------------------------------------------------- READ --------------------------------------------------

@router.get("/{image_id}", response_description="Get an image")
async def get_image(
    image_id: str = Path(..., description="Image UUID"),
    env=Depends(get_env),
):
    """Handles GET /image requests"""
    image_directory = env.IMAGE_DIRECTORY
    try:
        with PILOpen(image_directory, f"{image_id}.png") as image_file:
            return ImageResponse(image_file)
    except ImageError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Image with id {image_id} not found")


@router.get("/{image_id}/rotated", response_class=FileResponse, response_description="Get a rotated image")
async def get_rotated_image(
    image_id: str = Path(..., description="Image UUID"),
    direction: str | None = Query(default="R", regex=r"^[LlRr]$", description=ROTATION_DIRECTION),
    degrees: int = Query(..., multiple_of=90, description=ROTATION_AMOUNT),
    env=Depends(get_env)
):
    """Handles GET /image requests, with rotation. Rotations must be a multiple of 90 degrees."""
    image_directory = env.IMAGE_DIRECTORY
    try:
        with PILOpen(image_directory, f"{image_id}.png") as image:
            # any multiple of 90 is valid, but we can discard any rotations that wrap around the circle
            degrees %= 360
            if direction not in {'L', 'l'}:
                # default rotation is left (cw); reverse the degrees around the circle for right (cw)
                degrees = abs(360 - degrees)
            match degrees:
                case 90:
                    image = image.transpose(PIL.Image.ROTATE_90)
                case 180:
                    image = image.transpose(PIL.Image.ROTATE_180)
                case 270:
                    image = image.transpose(PIL.Image.ROTATE_270)
            return ImageResponse(image)
    except ImageError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Image with id {image_id} not found")


@router.get("/{image_id}/resized", response_class=Response, response_description="Get a resized image")
async def get_resized_image(
    image_id: str = Path(..., description="Image UUID"),
    lock_aspect_ratio: bool | None = Query(default=True, description=LOCK_ASPECT_RATIO),
    width: int = Query(..., gt=0, description="New width (in pixels)"),
    height: int = Query(..., gt=0, description="New height (in pixels)"),
    env=Depends(get_env)
):
    """
    Handles GET /image requests, with resize. If the aspect ratio is locked, the image will be resized as much as
    possible in the dimension with the larger change. The image will be **at most** width x height pixels large,
    but with one dimension increased or decreased less than the other so that the aspect ratio is preserved.
    """
    image_directory = env.IMAGE_DIRECTORY
    try:
        with PILOpen(image_directory, f"{image_id}.png") as image:
            if not lock_aspect_ratio:
                image = image.resize((width, height))
            else:
                image.thumbnail((width, height))  # for some reason, this one mutates instead of returning a copy
            return ImageResponse(image)
    except ImageError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Image with id {image_id} not found")
