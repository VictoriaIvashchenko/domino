FROM jenkins/jenkins:lts
USER root
RUN apt-get update && apt-get -y install cmake && apt-get -y install build-essential