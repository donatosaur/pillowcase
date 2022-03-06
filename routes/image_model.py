# Author:      Donato Quartuccia
# Modified:    2022-03-06
# Description: Image model

from uuid import UUID
import pathlib
import traceback
from pydantic import BaseModel, validator
import PIL
import PIL.Image as Image

# exports
__all__ = ["ImageModel", "PILOpen", "ImageError"]


# --------------------------------------------------- Models ---------------------------------------------------

class ImageModel(BaseModel):
    """Model for image data"""
    image_id: UUID | str

    @validator("image_id")
    def validate_uuid(cls, image_id: str | UUID):
        """Pydantic validator; class method see https://pydantic-docs.helpmanual.io/usage/validators/"""
        if isinstance(image_id, UUID):
            return image_id
        else:
            return UUID(str(image_id), version=4)


# ---------------------------------------------- Context Manager ----------------------------------------------

class ImageError(Exception):
    """Raised when an Image cannot be opened"""
    pass


class PILOpen:
    """Context manager to handle opening PIL image files from disk"""

    def __init__(self, directory_path: str, filename: str):
        """
        :param directory_path: path to the directory containing the image file
        :param filename: name of the image file (including the extension)
        """
        try:
            self.image = Image.open(f"{directory_path}/{filename}")
        except (FileNotFoundError, ValueError, PIL.UnidentifiedImageError):
            # try to look for a file with another extension
            filename = filename[:filename.rindex('.')]
            for file in pathlib.Path(f"{directory_path}").glob(f"{filename}*"):
                try:
                    self.image = Image.open(file)
                    return
                except (FileNotFoundError, ValueError, PIL.UnidentifiedImageError):
                    pass
            raise ImageError

    def __enter__(self):
        return self.image

    def __exit__(self, exc_type, exc_val, exc_tb):
        if isinstance(exc_val, ValueError):
            # likely the file pointer was already closed/destroyed; log it and return true so we don't
            # propagate the error back up, otherwise the client will receive a 500
            print("ValueError in image_model.PILOpen.__exit__")
            traceback.print_tb(exc_tb)
            return True
        if self.image is not None:
            self.image.close()
