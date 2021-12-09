#!/bin/sh

# make dir for mounting local dir
mkdir src

# make sure packages upgraded
apk update
apk upgrade

#install other packages
apk add git
apk add vim
apk add build-base

# install python3 and pip3
apk add python3
apk add python3-dev
apk add libffi-dev
apk add py3-pip
apk add py3-pyzmq
apk add py3-pandas
apk add py3-beautifulsoup4

# install python requirements
pip3 -q install pip --upgrade
pip3 install -r build/requirements.txt

# remove dev stuff we don't need after build
apk del build-base
apk del python3-dev
apk del libffi-dev

# get source code
#mkdir -p /project
#git clone https://github.com/bobruddy/pa_education_data.git /project/pa_education_data
