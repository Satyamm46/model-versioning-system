// Declarative pipeline for the Model Versioning and Management System.
// Works on Linux/macOS agents (sh) and Windows agents (bat).

def run(String cmd) { if (isUnix()) { sh cmd } else { bat cmd } }
def venvPy()  { return isUnix() ? '.venv/bin/python' : '.venv\\Scripts\\python' }
def sysPy()   { return isUnix() ? 'python3' : 'python' }

pipeline {
    agent any

    options {
        disableConcurrentBuilds()
        timeout(time: 20, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    // Fallback if you do not set up a GitHub webhook: poll Git every 2 minutes.
    triggers { pollSCM('H/2 * * * *') }

    environment {
        MVS_PORT = '8000'
        // Stops Jenkins from killing the app it starts at the end of the build.
        JENKINS_NODE_COOKIE = 'dontKillMe'
    }

    stages {
        stage('Git Checkout') {
            steps { checkout scm }
        }

        stage('Install Dependencies') {
            steps {
                script {
                    run("${sysPy()} -m venv .venv")
                    run("${venvPy()} -m pip install --upgrade pip")
                    run("${venvPy()} -m pip install -r requirements.txt")
                }
            }
        }

        stage('Code Validation') {
            steps {
                script {
                    run("${venvPy()} -m compileall -q backend scripts tests")
                    run("${venvPy()} -m pyflakes backend scripts tests")
                }
            }
        }

        stage('Unit Testing') {
            steps { script { run("${venvPy()} -m pytest -v --junitxml=test-results.xml") } }
            post { always { junit allowEmptyResults: true, testResults: 'test-results.xml' } }
        }

        stage('Model Validation') {
            steps { script { run("${venvPy()} scripts/validate_model.py") } }
        }

        stage('Version Generation') {
            steps {
                script {
                    env.RELEASE_VERSION = "1.0.${env.BUILD_NUMBER}"
                    echo "Release version: ${env.RELEASE_VERSION}"
                }
            }
        }

        stage('Build') {
            steps {
                script { run("${venvPy()} scripts/build.py") }
                archiveArtifacts artifacts: 'dist/*.zip', fingerprint: true
            }
        }

        // Only reached if every previous stage passed. A failed stage stops the pipeline,
        // so a broken build is never deployed.
        stage('Deployment') {
            steps { script { run("${venvPy()} scripts/deploy.py") } }
        }

        stage('Health Check') {
            steps {
                script {
                    try {
                        run("${venvPy()} scripts/health_check.py")
                    } catch (err) {
                        echo 'Health check failed - switching back to the previous release'
                        run("${venvPy()} scripts/deploy.py --rollback")
                        error('Deployment rolled back after failed health check')
                    }
                }
            }
        }
    }

    post {
        success { echo "Build and deployment of ${env.RELEASE_VERSION} successful" }
        failure { echo 'Pipeline FAILED - nothing was deployed (or the release was rolled back)' }
    }
}
