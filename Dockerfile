FROM nginx:1.28-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY pde_site /usr/share/nginx/html

# nginx gzip_static serves name.json from name.json.gz.
RUN find /usr/share/nginx/html -type f -name '*.json' -exec gzip -9n {} +
