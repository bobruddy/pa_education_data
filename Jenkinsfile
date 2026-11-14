pipeline {
    agent { label 'education' }
    options {
        disableConcurrentBuilds(abortPrevious: true)
    }
    stages {
        stage('test') {
            steps {
                sh '''
                    set -eu
                    python3 -m venv .venv
                    .venv/bin/pip install -e '.[dev]'
                    .venv/bin/pytest tests/ -q
                '''
            }
        }
        stage('data') {
            steps {
                sh '''
                    set -eu
                    tag=$(git rev-parse HEAD)
                    image="192.168.150.59:443/pde-data:${tag}"
                    docker build -f Dockerfile.data -t "$image" .
                    docker push "$image"
                    scripts/docker09-data.sh "$tag"
                    ssh docker09 'set -eu
                        ready=0
                        for _ in 1 2 3 4 5 6 7 8 9 10; do
                            if docker exec pde-data python -c "import pa_edu.refine"; then
                                ready=1
                                break
                            fi
                            sleep 2
                        done
                        test "$ready" = 1
                        docker exec pde-data python -m pa_edu.refine
                        docker exec pde-data python -m pa_edu.personnel
                        docker exec pde-data python -m pa_edu.check
                    '
                '''
            }
        }
        // Site publish and the nginx image stay off until the data container
        // has been checked. Restore both stages after that.
    }
}
