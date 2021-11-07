# Files for generating docker images to run this to satisfy dependancies

## I use the following command to build this image
This assumes you are located in the directory of the Dockerfile
```
docker build -t pa_education .
```

## I use the following command to run this image
This assumes you are in your local directory you want to be the base for your jupyter notebook. So normally I start this in my pa_education_data git repo

```
docker run -p 8889:8888 -v "${PWD}":/home/jovyan/work pa_education
```

Once started you can navigate to the 127.0.0.1 URL that is printed out
