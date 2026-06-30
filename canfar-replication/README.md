# Introduction

This project is specifically designed to create Replication Rules in Harbor through terraform and attach labels to the artifacts to make them available in CANFAR

## Terraform script

Assuming user already have the terraform setup and configured.

Create a variables.auto.tfvars in ```canfar-replication/tf/``` directory [Follow the variables.auto.tfvars.example]
Add the new labels in ```canfar-replication/tf/variables.tf``` if there are any otherwise the existing labels are already there

Use the following command to setup the replication rules in Harbor

```
tofu fmt
tofu validate
tofu plan
tofu apply
```

## Python Script

Once the Replication rules are there you'd need to be patient or wait until the replication is done (cronjob are configured to execute the replications but you can trigger them manually)

Once the aritfacts are synced you are now ready to label them

### Prereqs

#### Python

Update the projects list in canfar-replication/python/config.py if there's any

Create a python environment in canfar-replication/python

```
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Export the environment variables

```
export HARBOR_DEST_URL=https://<dest_url>
export HARBOR_USER=<username>
export HARBOR_PASS=<password>
export HARBOR_REMOTE_URL=https://<remote_url>
```

Execute the script

```
python main.py
```

#### Run python in container

You can also create a docker image to run the python script in a container.

```
cd canfar-replication/python
docker build --platform linux/amd64,linux/arm64 -t <registry-url>/harbor/harbor-labeler:1.0.0 .
docker push <registry-url>/harbor/harbor-labeler:1.0.
```

Make sure to login into registry if it is a secure one.
And in harbor you also need to set the project as public.
