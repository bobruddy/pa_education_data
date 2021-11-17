# start with this baseline
FROM alpine:latest

# upgrade pip3 and install requirements
RUN mkdir build
COPY . build/
RUN /bin/sh build/install.sh

# run jupyter
#WORKDIR /home/jovyan/work
#CMD ["jupyter", "notebook", "--port=8888", "--no-browser", "--ip=0.0.0.0", "--allow-root"]
CMD /bin/sh -l
