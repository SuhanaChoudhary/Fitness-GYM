pipeline {
    agent any

    environment {
        IMAGE_NAME = 'aceest-fitness'
        IMAGE_TAG  = "build-${env.BUILD_NUMBER}"
    }

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 20, unit: 'MINUTES')
    }

    stages {
        stage('Checkout') {
            steps {
                echo 'Pulling the latest source from GitHub'
                checkout scm
                sh 'git log -1 --oneline'
            }
        }

        stage('Build Docker Image') {
            steps {
                echo 'Building a clean ACEest image from the Dockerfile'
                sh 'docker build --target test -t ${IMAGE_NAME}:${IMAGE_TAG}-test .'
                sh 'docker build --target runtime -t ${IMAGE_NAME}:${IMAGE_TAG} .'
            }
        }

        stage('Quality Gate: Pytest') {
            steps {
                echo 'Executing the Pytest suite inside the build container'
                sh 'docker run --rm ${IMAGE_NAME}:${IMAGE_TAG}-test pytest -v --junitxml=/tmp/results.xml || exit 1'
            }
        }

        stage('Quality Gate: Lint') {
            steps {
                sh 'docker run --rm ${IMAGE_NAME}:${IMAGE_TAG}-test flake8 app.py fitness.py models.py tests'
            }
        }

        stage('Smoke Test') {
            steps {
                sh '''
                    docker rm -f aceest-smoke-${BUILD_NUMBER} >/dev/null 2>&1 || true
                    docker run -d --name aceest-smoke-${BUILD_NUMBER} -P ${IMAGE_NAME}:${IMAGE_TAG}
                    PORT=$(docker port aceest-smoke-${BUILD_NUMBER} 5000/tcp | cut -d: -f2)
                    for i in $(seq 1 15); do
                        if curl -fsS http://localhost:${PORT}/health; then
                            docker rm -f aceest-smoke-${BUILD_NUMBER}
                            exit 0
                        fi
                        sleep 2
                    done
                    docker logs aceest-smoke-${BUILD_NUMBER}
                    docker rm -f aceest-smoke-${BUILD_NUMBER}
                    exit 1
                '''
            }
        }
    }

    post {
        always {
            echo 'Cleaning up temporary build images'
            sh 'docker rmi -f ${IMAGE_NAME}:${IMAGE_TAG}-test ${IMAGE_NAME}:${IMAGE_TAG} || true'
        }
        success {
            echo 'BUILD SUCCESS - the ACEest image passed every quality gate.'
        }
        failure {
            echo 'BUILD FAILED - inspect the stage logs above.'
        }
    }
}
