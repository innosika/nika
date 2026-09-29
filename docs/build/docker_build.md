# Build the project using Docker

## Requirements

You will need [Docker](https://docs.docker.com/) (with Compose plugin) installed and running on your machine.

We recommend using Docker Desktop on [macOS](https://docs.docker.com/desktop/install/mac-install/) / [Windows](https://docs.docker.com/desktop/install/windows-install/) and using [Docker Server](https://docs.docker.com/engine/install/#server) distribution for your Linux distribution of choice. Use installation instructions provided in the links above.

## Installation

```sh
git clone -c core.longpaths=true -c core.autocrlf=true https://github.com/ostis-apps/nika # this avoids problems on Windows filesystems
cd nika
git submodule update --init --recursive
docker compose pull
```

The `problem-solver` image is not published on Docker Hub, so `docker compose pull`
skips it (the service is marked `pull_policy: build`) and it must be built locally.

## Build

  ```sh
  docker compose build problem-solver
  ```

  Building only `problem-solver` is enough — the other images are pulled from Docker Hub.
  Use `docker compose build` to rebuild all of them from source instead.

## 🚀 Run

  ```sh
  docker compose up --no-build
  ```

  This command will launch 2 Web UIs on your machine:
  
- sc-web - `localhost:8000`
- dialogue web UI - `localhost:3033`

**We've set our system to rebuild KB on each restart**. If you're debugging some specific subset of your knowledge base you may want to change repo.path to exclude the folders you don't need.

**If you do not want to rebuild KB on relaunch**, you can comment out the `REBUILD_KB` environment variable in `docker-compose.yml`.
You can use `docker compose run --rm problem-solver build` to rebuild KB manually.

## Troubleshooting

Common issues:

- `docker compose pull` fails with `failed to resolve reference "docker.io/ostis/nika:0.2.2": not found`

  **Solution**: this image is built from this repository rather than pulled. Run `docker compose build problem-solver` once, then launch as usual.

- The `problem-solver` build fails with `ERROR: Package 'sc-machine/0.10.4' not resolved: ... [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: certificate has expired`

  The `sc-machine` and `scl-machine` Conan packages are only hosted on `conan.ostis.net` (they are not on conancenter), and the TLS certificate of that server expired on 2026-08-08. The server itself is up and answers normally over an unverified connection.

  **Solution**: either wait until the certificate is renewed, or build with certificate verification disabled for that single remote:
  ```sh
  CONAN_INSECURE_REMOTE=1 docker compose build problem-solver
  ```
  Note the trade-off: with `CONAN_INSECURE_REMOTE=1` the dependencies are downloaded over a TLS connection that is not verified, so a man-in-the-middle could substitute the packages your image is built from. Use it only if you accept that risk, and drop it once the certificate is valid again.

Windows-specific problems:

- Docker images built on your computer are not launching correctly and logging something along these lines: `bash\r: No such file or directory`

    **Solution**: please make sure your Git repo is configured to be compatible UNIX line endings

    ```sh
    cd nika
    git config --local core.autocrlf true
    ```

- Git cannot clone repos or submodules, error looks like `error: unable to create file ... (file too long)`

    **Solution**: please make sure your Git repo has `longpaths` config option enabled:

    ```sh
    cd nika
    git config --local core.longpaths true
    ```

Common issues:

- Docker images cannot be built locally. Error: `status: the --mount option requires BuildKit`

    **Solution**: Please note that you'd only need it for custom images, you can launch our system without building images yourself. Use the [Docker Docs BuildKit reference](https://docs.docker.com/go/buildkit) to enable Docker BuildKit on your computer. **In case you're using Windows**, you could use `$env:DOCKER_BUILDKIT = 1` while building in PowerShell.

- Help! My `problem-solver` container is `unhealthy`

    Looks like your container didn't start properly. There are two main reasons for this: violated `start_period` (in case it naturally takes a lot of time to launch our system on your hardware) or faulty server instance. Since there are 2 reasons to this problem, we'll provide 2 solutions.

    **Solution 1**: Increasing `start_period` in `docker-compose.yml` might help you.
    
    **Solution 2**: Check [known issues](https://github.com/ostis-apps/nika/issues), and in case your problem is not reported yet, create a new one! 
