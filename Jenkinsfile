pipeline {
	agent any

	stages {
		stage('Build') {
			steps {
				sh 'docker build -t w3rcr/batch_test \
					-f docker_files/production/Dockerfile docker_files/production' 
				sh 'docker push w3rcr/batch_test'
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
