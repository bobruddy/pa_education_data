# start with this baseline
FROM jupyter/scipy-notebook

# upgrade pip3 and install requirements
RUN mkdir build
WORKDIR build/
COPY . .
RUN pip3 -q install pip --upgrade
RUN pip3 install -r requirements.txt

# run jupyter
CMD ["jupyter", "notebook", "--port=8888", "--no-browser", "--ip=0.0.0.0", "--allow-root"]
