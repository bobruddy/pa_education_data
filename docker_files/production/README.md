# Production Docker image (legacy)

> **Legacy.** The live site is a static tree built by `python -m pa_edu.publish` and rsynced to elm (`https://pdenumbers.org/`). Jenkins still builds this image as `w3rcr/batch_test`; it is not the deploy path for the LEA browser.

Build from this directory:

```bash
docker build -t pa_education .
```

The image clones / expects this repo and is aimed at batch notebook work, not at serving `pde_site/`.
