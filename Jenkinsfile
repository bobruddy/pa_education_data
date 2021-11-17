pipeline {
	agent any

	stages {
		stage('Build') {
			steps {
				sh 'docker build -t pa_education \
					-f docker_files/development/Dockerfile .' 
			}
		}
		stage('Test') {
			steps {
				echo 'Your test steps...'
			}
		}
		stage('Deploy') {
			steps {
				echo 'Deploy your application...'
			}
		}
	}
}
