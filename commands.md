# Setting up Hosts

1. ` sudo nano /etc/hosts `
2. Add the following lines to the file:

        {YOUR_SERVER_IP} mlflow.openiiot.mlops
        {YOUR_SERVER_IP} lakefs.openiiot.mlops
        {YOUR_SERVER_IP} seaweed.openiiot.mlops

    Replace `{YOUR_SERVER_IP}` with the actual IP address of your server.

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