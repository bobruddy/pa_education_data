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
                    mkdir -p /home/jenkins/pde-data
                    rm -rf data
                    ln -s /home/jenkins/pde-data data
                    .venv/bin/python -m pa_edu.refine
                    .venv/bin/python -m pa_edu.personnel
                    .venv/bin/python -m pa_edu.check
                '''
            }
        }
        stage('publish') {
            steps {
                sh '''
                    set -eu
                    .venv/bin/python -m pa_edu.publish
                '''
            }
        }
    }
}
