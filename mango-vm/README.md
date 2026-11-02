# How to access Mango-vm with OPKSSH

1. Install OPKSSH on to your local machine here: https://github.com/openpubkey/opkssh - follow the steps below depending on your systemOS, the easiest way to do this on a MAC is with brew:

```
brew tap openpubkey/opkssh
brew install opkssh
```

Or alternativly: please note if you choose the alternative you need to run a sudo mv opkssh /usr/local/bin/ afterwards to manually move your OPKSSH into your /usr/local/bin/.

```
curl -L https://github.com/openpubkey/opkssh/releases/latest/download/opkssh-osx-amd64 -o opkssh; chmod +x opkssh
```

2. Create folder to store your OPKSSH credientials

```
 mkdir -p ~/.opk
```

3. run `nano ~/.opk/config.yml` & copy in the below:

```
--
default_provider: skaiam

providers:

  - alias: skaiam
    issuer: https://ska-iam.stfc.ac.uk/
    client_id: 2c4c4d8e-d577-42ad-a798-743201578a61
    scopes: openid email profile
    access_type: offline
    prompt: consent
    redirect_uris:
      - http://localhost:3000/login-callback
      - http://localhost:10001/login-callback
      - http://localhost:11110/login-callback
```

4. Modify your .ssh/config file using `nano ~/.ssh/config` - please note to change "your-username" to your SKAIAM username:

```
Host mango
        User your-username
        Hostname 130.246.214.241
	IdentityAgent "~/.ssh/id_ecdsa"
        ForwardAgent yes
```

5. Run: `opkssh login skaiam` this will create a new window in your browser to verify your login using SKAIAM - Please select promt me again next time to avoid issues.

6. Finally run:
   `ssh mango`
   to access the Virtual Machine.
