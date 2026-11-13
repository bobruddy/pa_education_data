pipeline {
    agent any
    stages {
        stage('test') {
            steps {
                sh '''
                    set -eu
                    if ! python3 -c 'import ensurepip' 2>/dev/null; then
                        sudo DEBIAN_FRONTEND=noninteractive apt-get update
                        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv
                    fi
                    python3 -m venv .venv
                    .venv/bin/pip install -e '.[dev]'
                    .venv/bin/pytest tests/ -q
                '''
            }
        }
        stage('publish') {
            steps {
                sh '''
                    set -eu
                    data=/var/lib/jenkins/pde-data
                    if [ ! -f "$data/refined/lea.parquet" ] || [ ! -f "$data/pde.db" ]; then
                        echo "missing $data. From a checkout that has data/, run scripts/push-jenkins-data.sh" >&2
                        exit 1
                    fi
                    mkdir -p data
                    rm -rf data/refined data/pde.db
                    ln -s "$data/refined" data/refined
                    ln -s "$data/pde.db" data/pde.db
                    .venv/bin/python -m pa_edu.publish
                '''
            }
        }
    }
}
