# start with this baseline
FROM alpine:edge

EXPOSE 8080
EXPOSE 8050

# upgrade pip3 and install requirements
RUN mkdir build
RUN mkdir /working
COPY . build/
RUN /bin/sh build/install.sh

# run jupyter
WORKDIR /working
CMD ["jupyter", "notebook", "--port=8888", "--no-browser", "--ip=0.0.0.0", "--allow-root"]
#CMD /bin/sh -l
