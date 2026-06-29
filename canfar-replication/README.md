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

Execute the script

```
python label_artifacts.py
```
