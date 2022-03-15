# Author:      Donato Quartuccia
# Modified:    2022-03-15
# Description: Image controller

import uuid
import glob
from typing import Final
from io import BytesIO

from fastapi import APIRouter, HTTPException, Depends, Path, Query, UploadFile
from fastapi.responses import FileResponse, Response
from starlette import status

import PIL
from PIL.Image import (
    Image,
    open as image_from_bytestream  # only use on bytestream from request; otherwise use PILOpen
)

from .image_model import ImageModel, PILOpen, ImageError
from config import get_env


router = APIRouter(prefix="/image", tags=["image"])


# ------------------------------------------- Constants --------------------------------------------

ROTATION_DIRECTION: Final = "'R' for right/clockwise (default), 'L' for left/counterclockwise"
ROTATION_AMOUNT: Final = "A multiple of 90 degrees"
LOCK_ASPECT_RATIO: Final = "True to lock the aspect ratio (default). False to leave it unlocked. " \
                           "Note that leaving it unlocked may result in a stretched image."


# -------------------------------------------- Helpers ---------------------------------------------
def ImageResponse(image: Image) -> Response:
    """
    Helper for sending PIL image file responses
    :param image: the PIL image file to send
    """
    # PIL.Image.tobytes() doesn't work correctly on compressed image formats; instead, we need to
    # use a stream: see pillow.readthedocs.io/en/stable/reference/Image.html?highlight=tobytes()
    buffer = BytesIO()
    try:
        image.save(buffer, format="png")
        return Response(buffer.getvalue(), media_type="image/png")
    finally:
        buffer.close()


def get_unique_image_id(image_directory) -> uuid:
    """
    Generates a unique UUID for a file in image_directory
    :param image_directory: directory to be checked for UUID collisions
    """
    image_id = uuid.uuid4()
    while glob.glob(f"{image_directory}/{image_id}*"):
        image_id = uuid.uuid4()
    return image_id


def validate_image_file_request(image_file: UploadFile):
    """
    Validates the specified image file
    :raise HTTPException: if the specified image_file does not exist or has an invalid MIME type
    """
    if not image_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing file",
        )
    elif not image_file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Invalid content type",
        )


def raise_HTTPException_from_PIL_image(error: Exception):
    """
    :param error: PIL.UnidentifiedImageError or PIL.Image.DecompressionBombWarning
    :raise HTTPException: an HTTPException response based on the type of error
    """
    if isinstance(error, PIL.UnidentifiedImageError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported file type")
    elif isinstance(error, PIL.Image.DecompressionBombWarning):
        # see the discussion at: pillow.readthedocs.io/en/stable/reference/Image.html#functions
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum file size exceeded: {PIL.Image.MAX_IMAGE_PIXELS} pixels"
        )
    else:
        raise  # unhandled; propagate up and return a 500


# --------------------------------------------- CREATE ---------------------------------------------

@router.post("/", response_description="Upload an image", response_model=ImageModel)
async def post_image(
    image_file: UploadFile,
    env=Depends(get_env),
):
    """
    Handles /image POST requests with a file. The request must contain media with an image MIME type
    """
    validate_image_file_request(image_file)
    try:
        # read the bytestream from the request and attempt to open it as an image
        with image_from_bytestream(image_file.file) as image_file:
            image_id = get_unique_image_id(env.IMAGE_DIRECTORY)
            image_file.save(f"{env.IMAGE_DIRECTORY}/{image_id}.png", "png")
            return {"image_id": str(image_id)}  # UUID -> hex
    except (PIL.UnidentifiedImageError, PIL.Image.DecompressionBombWarning) as error:
        raise_HTTPException_from_PIL_image(error)


# -------------------------------------------- READ -----------------------------------------------

@router.get("/{image_id}", response_description="Get an image")
async def get_image(
    image_id: str = Path(..., description="Image UUID"),
    env=Depends(get_env),
):
    """Handles GET /image requests"""
    try:
        with PILOpen(env.IMAGE_DIRECTORY, f"{image_id}.png") as image_file:
            return ImageResponse(image_file)
    except ImageError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image with id {image_id} not found",
        )


@router.get(
    "/{image_id}/rotated",
    response_class=FileResponse,
    response_description="Get a rotated image",
)
async def get_rotated_image(
    image_id: str = Path(..., description="Image UUID"),
    direction: str | None = Query(default="R", regex=r"^[LlRr]$", description=ROTATION_DIRECTION),
    degrees: int = Query(..., multiple_of=90, description=ROTATION_AMOUNT),
    env=Depends(get_env),
):
    """Handles GET /image requests, with rotation. Rotations must be a multiple of 90 degrees."""
    try:
        with PILOpen(env.IMAGE_DIRECTORY, f"{image_id}.png") as image:
            degrees %= 360  # discard rotations that wrap around the circle
            if direction not in {'L', 'l'}:
                degrees = abs(360 - degrees)  # default is ccw (left); reverse degrees for cw
            match degrees:
                case 90:
                    image = image.transpose(PIL.Image.ROTATE_90)
                case 180:
                    image = image.transpose(PIL.Image.ROTATE_180)
                case 270:
                    image = image.transpose(PIL.Image.ROTATE_270)
            return ImageResponse(image)
    except ImageError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image with id {image_id} not found",
        )


@router.get(
    "/{image_id}/resized",
    response_class=Response,
    response_description="Get a resized image",
)
async def get_resized_image(
    image_id: str = Path(..., description="Image UUID"),
    lock_aspect_ratio: bool | None = Query(default=True, description=LOCK_ASPECT_RATIO),
    width: int = Query(..., gt=0, description="New width (in pixels)"),
    height: int = Query(..., gt=0, description="New height (in pixels)"),
    env=Depends(get_env)
):
    """
    Handles GET /image requests, with resize. If the aspect ratio is locked, the image will be
    resized as much as possible in the dimension with the larger change. The image will be at most
    width x height pixels large, but with one dimension increased or decreased less than the other.
    """
    try:
        with PILOpen(env.IMAGE_DIRECTORY, f"{image_id}.png") as image:
            if not lock_aspect_ratio:
                image = image.resize((width, height))
            else:
                image.thumbnail((width, height))  # this one mutates instead of returning a copy
            return ImageResponse(image)
    except ImageError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image with id {image_id} not found",
        )
