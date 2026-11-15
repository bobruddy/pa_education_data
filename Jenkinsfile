pipeline {
    agent { label 'education' }
    options {
        disableConcurrentBuilds(abortPrevious: true)
    }
    triggers {
        // Daily acquisition / model refresh. No site image on a timer build.
        cron('H 6 * * *')
    }
    parameters {
        booleanParam(
            name: 'FORCE_DATA_REFRESH',
            defaultValue: false,
            description: 'Rebuild the data image and run refine/personnel/check even when data code is unchanged'
        )
    }
    stages {
        stage('decide') {
            steps {
                script {
                    def timed = !currentBuild.getBuildCauses('hudson.triggers.TimerTrigger$TimerTriggerCause').isEmpty()
                    def forced = params.FORCE_DATA_REFRESH
                    def changed = sh(script: 'chmod +x scripts/data-code-changed.sh scripts/refresh-data.sh scripts/docker09-data.sh scripts/docker09.sh; scripts/data-code-changed.sh', returnStatus: true) == 0
                    env.DO_DATA_REFRESH = (timed || forced || changed) ? '1' : '0'
                    // Timer builds refresh data only. SCM / manual builds still publish the site.
                    env.DO_SITE_BUILD = timed ? '0' : '1'
                    echo "timed=${timed} forced=${forced} dataCodeChanged=${changed} DO_DATA_REFRESH=${env.DO_DATA_REFRESH} DO_SITE_BUILD=${env.DO_SITE_BUILD}"
                }
            }
        }
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
            when {
                environment name: 'DO_DATA_REFRESH', value: '1'
            }
            steps {
                sh '''
                    set -eu
                    tag=$(git rev-parse HEAD)
                    image="192.168.150.59:443/pde-data:${tag}"
                    docker build -f Dockerfile.data --build-arg PDE_GIT_SHA="$tag" -t "$image" .
                    docker push "$image"
                    scripts/docker09-data.sh "$tag"
                    scripts/refresh-data.sh
                '''
            }
        }
        stage('publish') {
            when {
                environment name: 'DO_SITE_BUILD', value: '1'
            }
            steps {
                sh '''
                    set -eu
                    export PDE_REFINED_URL=http://192.168.10.116:8091/refined
                    .venv/bin/python -m pa_edu.publish
                '''
            }
        }
        stage('image') {
            when {
                environment name: 'DO_SITE_BUILD', value: '1'
            }
            steps {
                sh '''
                    set -eu
                    tag=$(git rev-parse HEAD)
                    image="192.168.150.59:443/pdenumbers:${tag}"
                    docker build -t "$image" -t "192.168.150.59:443/pdenumbers:latest" .
                    docker push "$image"
                    docker push "192.168.150.59:443/pdenumbers:latest"
                    scripts/docker09.sh "$tag"
                '''
            }
        }
    }
}
