# Setting up Hosts

1. ` sudo nano /etc/hosts `
2. Add the following lines to the file:

        {YOUR_SERVER_IP} mlflow.openiiot.mlops
        {YOUR_SERVER_IP} lakefs.openiiot.mlops
        {YOUR_SERVER_IP} seaweed.openiiot.mlops

    Replace `{YOUR_SERVER_IP}` with the actual IP address of your server.