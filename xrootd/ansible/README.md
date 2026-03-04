
# xrootd installation

An ansible playbook for installing and configuring xrootd for SKA/UKSRC.

- Installs xrootd
- Configures xrootd for use with SKA-IAM
- Generate self-signed cert (if no pre-existing certs are listed)
- Sets xrootd to use port 1094
- Sets up directory for xrootd data to be sorted
- Optionally: Setup Rucio access


## To run:
- **Only works on ubuntu 24.04 and Rocky9**
- **Rucio only works with Rocky9**
- Place hosts in `inventory` file
- `ansible-playbook xrootd.yml -i inventory `

## Configuring
Variables are found in `group_vars/all/variables.yml`
- `site_name`: the name of the xrootd instance (needed for Rucio) (Default: `test-site`)
- `cert_path`: path to SSL cert (if left blank will generate self-signed cert)
- `key_path`: path to cer key (If left blank will generate self-signed cert)
- `data_path`: path where xrootd data will be stored (Default: `/data` **It is highly recomended that the path is kept at top level like /data**)
- `rucio`: whether to set up rucio config (Default: `false`)
- `remote_user`: the user for ansible to log in as if applying playbook to another machine
