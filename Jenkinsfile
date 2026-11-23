pipeline {
    agent any

    parameters {
        booleanParam(
            name: 'RUN_SONARQUBE',
            defaultValue: false,
            description: 'Run SonarQube analysis and enforce its Quality Gate.'
        )
        booleanParam(
            name: 'PUBLISH_IMAGE',
            defaultValue: false,
            description: 'Push versioned images to Docker Hub or another OCI registry.'
        )
        string(
            name: 'REGISTRY_HOST',
            defaultValue: 'docker.io',
            description: 'Container registry host.'
        )
        string(
            name: 'IMAGE_REPOSITORY',
            defaultValue: 'your-dockerhub-user/aceest-fitness',
            description: 'Registry repository without a tag.'
        )
        string(
            name: 'RELEASE_VERSION',
            defaultValue: 'v1.0',
            description: 'Version prefix; Jenkins appends the build number.'
        )
        choice(
            name: 'DEPLOY_STRATEGY',
            choices: ['none', 'rolling', 'blue-green', 'canary', 'shadow', 'ab'],
            description: 'Optional Kubernetes deployment strategy.'
        )
        string(
            name: 'BASELINE_IMAGE',
            defaultValue: '',
            description: 'Stable image used beside the candidate for progressive strategies.'
        )
    }

    environment {
        IMAGE_NAME = 'aceest-fitness'
        LOCAL_TAG = "build-${env.BUILD_NUMBER}"
        SONARQUBE_INSTALLATION = 'ACEest SonarQube'
        SONAR_SCANNER_TOOL = 'SonarScanner'
    }

    triggers {
        pollSCM('H/5 * * * *')
    }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 30, unit: 'MINUTES')
    }

    stages {
        stage('Clean Checkout') {
            steps {
                deleteDir()
                echo 'Pulling the latest source from GitHub into a clean workspace'
                checkout scm
                sh 'git log -1 --oneline'
                script {
                    env.GIT_SHA = sh(
                        script: 'git rev-parse --short=12 HEAD',
                        returnStdout: true
                    ).trim()
                    env.RELEASE_TAG = "${params.RELEASE_VERSION}.${env.BUILD_NUMBER}"
                    env.RELEASE_IMAGE = (
                        "${params.REGISTRY_HOST}/${params.IMAGE_REPOSITORY}:${env.RELEASE_TAG}"
                    )
                }
                sh 'mkdir -p reports'
                writeFile(
                    file: 'reports/build-metadata.txt',
                    text: """build=${env.BUILD_NUMBER}
git_sha=${env.GIT_SHA}
release_image=${env.RELEASE_IMAGE}
"""
                )
            }
        }

        stage('Build Docker Images') {
            steps {
                echo 'Building controlled test and runtime images from the Dockerfile'
                sh 'docker build --pull --target test -t ${IMAGE_NAME}:${LOCAL_TAG}-test .'
                sh 'docker build --pull --target runtime -t ${IMAGE_NAME}:${LOCAL_TAG} .'
            }
        }

        stage('Quality Gate: Pytest') {
            steps {
                echo 'Executing tests and coverage inside the build container'
                sh '''
                    docker run --rm \
                      --user "$(id -u):$(id -g)" \
                      -e COVERAGE_FILE=/tmp/.coverage \
                      -v "$WORKSPACE/reports:/reports" \
                      ${IMAGE_NAME}:${LOCAL_TAG}-test \
                      pytest -v -p no:cacheprovider \
                        --junitxml=/reports/pytest.xml \
                        --cov=app --cov=fitness --cov=models \
                        --cov-report=term-missing \
                        --cov-report=xml:/reports/coverage.xml
                '''
            }
        }

        stage('Quality Gate: Lint') {
            steps {
                sh 'docker run --rm ${IMAGE_NAME}:${LOCAL_TAG}-test flake8 app.py fitness.py models.py tests'
            }
        }

        stage('SonarQube Analysis') {
            when {
                expression { params.RUN_SONARQUBE }
            }
            steps {
                script {
                    def scannerHome = tool env.SONAR_SCANNER_TOOL
                    withSonarQubeEnv(env.SONARQUBE_INSTALLATION) {
                        sh "${scannerHome}/bin/sonar-scanner"
                    }
                }
            }
        }

        stage('Quality Gate: SonarQube') {
            when {
                expression { params.RUN_SONARQUBE }
            }
            options {
                timeout(time: 10, unit: 'MINUTES')
            }
            steps {
                waitForQualityGate abortPipeline: true
            }
        }

        stage('Smoke Test') {
            steps {
                sh '''
                    docker rm -f aceest-smoke-${BUILD_NUMBER} >/dev/null 2>&1 || true
                    docker run -d --name aceest-smoke-${BUILD_NUMBER} -P \
                      ${IMAGE_NAME}:${LOCAL_TAG}
                    PORT=$(docker port aceest-smoke-${BUILD_NUMBER} 5000/tcp \
                      | head -1 | sed 's/.*://')
                    for attempt in $(seq 1 15); do
                        if curl -fsS "http://localhost:${PORT}/health"; then
                            echo 'Health check passed'
                            docker rm -f aceest-smoke-${BUILD_NUMBER}
                            exit 0
                        fi
                        sleep 2
                    done
                    docker logs aceest-smoke-${BUILD_NUMBER}
                    exit 1
                '''
            }
        }

        stage('Publish Versioned Image') {
            when {
                expression { params.PUBLISH_IMAGE }
            }
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'container-registry-credentials',
                    usernameVariable: 'REGISTRY_USERNAME',
                    passwordVariable: 'REGISTRY_PASSWORD'
                )]) {
                    sh '''
                        test "$IMAGE_REPOSITORY" != 'your-dockerhub-user/aceest-fitness'
                        echo "$REGISTRY_PASSWORD" | docker login "$REGISTRY_HOST" \
                          --username "$REGISTRY_USERNAME" --password-stdin
                        docker tag ${IMAGE_NAME}:${LOCAL_TAG} "$RELEASE_IMAGE"
                        docker tag ${IMAGE_NAME}:${LOCAL_TAG} \
                          "${REGISTRY_HOST}/${IMAGE_REPOSITORY}:${GIT_SHA}"
                        docker tag ${IMAGE_NAME}:${LOCAL_TAG} \
                          "${REGISTRY_HOST}/${IMAGE_REPOSITORY}:latest"
                        docker push "$RELEASE_IMAGE"
                        docker push "${REGISTRY_HOST}/${IMAGE_REPOSITORY}:${GIT_SHA}"
                        docker push "${REGISTRY_HOST}/${IMAGE_REPOSITORY}:latest"
                        docker logout "$REGISTRY_HOST"
                    '''
                }
            }
        }

        stage('Deploy to Kubernetes') {
            when {
                allOf {
                    expression { params.PUBLISH_IMAGE }
                    expression { params.DEPLOY_STRATEGY != 'none' }
                }
            }
            steps {
                withCredentials([
                    string(credentialsId: 'aceest-secret-key', variable: 'ACEEST_SECRET_KEY'),
                    string(
                        credentialsId: 'aceest-admin-password',
                        variable: 'ACEEST_ADMIN_PASSWORD'
                    )
                ]) {
                    sh '''
                        export BASELINE_IMAGE="$BASELINE_IMAGE"
                        bash scripts/deploy.sh "$DEPLOY_STRATEGY" "$RELEASE_IMAGE"
                    '''
                }
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true, testResults: 'reports/pytest.xml'
            archiveArtifacts(
                allowEmptyArchive: true,
                artifacts: 'reports/**,k8s/**,sonar-project.properties',
                fingerprint: true
            )
            sh '''
                docker rm -f aceest-smoke-${BUILD_NUMBER} >/dev/null 2>&1 || true
                docker rmi -f ${IMAGE_NAME}:${LOCAL_TAG}-test \
                  ${IMAGE_NAME}:${LOCAL_TAG} >/dev/null 2>&1 || true
            '''
        }
        success {
            echo 'BUILD SUCCESS - every enabled quality gate passed.'
        }
        failure {
            echo 'BUILD FAILED - inspect the first failed stage.'
        }
    }
}
