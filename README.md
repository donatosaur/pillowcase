# Pillowcase
A simple API that wraps Pillowcase for Resize and Rotate requests via HTTP

### Environment Variables
Define the following env variables in `.env`:
* HOST: the server's hostname *(default: localhost)*
* PORT: the port the server should listen on *(default: 8000)*
* DEBUG_MODE: if set, the server will monitor for changes and reload; should be False in production *(default: False)*
* IMAGE_DIRECTORY: path to a directory where images received via POST should be stored **(required)**
