# Commands for lakeFS

## Setting up the environment variables

` lakectl config ` and set the prompted variables as set up in the `.env` file.

## Pulling Data from lakeFS

` lakectl fs download lakefs:{REPOSITORY}/{BRANCH}/ ./{FOLDER} --recursive `

Example: ` lakectl fs download lakefs://quickstart/main/ ./images --recursive `

## Pushing Data to lakeFS

Creating the request

` lakectl fs upload ./{FOLDER} lakefs:{REPOSITORY}/{BRANCH}/ --recursive `

Example: `lakectl fs upload   lakefs://quickstart/main/samples   --source samples   --recursive`

and then committing ...

` lakectl commit lakefs:{REPOSITORY}/{BRANCH}/ -m "Commit message" `

Example: `lakectl commit lakefs://quickstart/main -m "uploading samples"`