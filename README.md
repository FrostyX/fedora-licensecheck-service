# fedora-licensecheck-service

This is a proof of concept of continuously validating licenses for
every package build in Fedora.


## Running

### Run from git repository

Run the fedora-review-service consumer

```bash
PYTHONPATH=. fedora-messaging --conf conf/fedora.toml consume --callback="fedora_licensecheck_service.consumer:consume"
```
