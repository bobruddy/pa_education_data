# Development Docker image (legacy)

> **Legacy.** Day-to-day work uses a local venv and the refined pipeline (`python -m pa_edu.refine`). See the repo [README](../../README.md). This Alpine image starts Jupyter for the older notebooks.

Build from this directory:

```bash
docker build -t pa_education .
```

Run with the repo mounted at the image workdir (`/working`):

```bash
docker run -p 8888:8888 -v "${PWD}/../..":/working pa_education
```

Open the `127.0.0.1:8888` URL printed in the logs (include the token). Detached runs need `docker logs` for that URL.
