FROM node:20-bookworm-slim AS build

ARG TARO_APP_API_BASE_URL=/api
ENV TARO_APP_API_BASE_URL=${TARO_APP_API_BASE_URL} \
    HUSKY=0

WORKDIR /app
COPY miniapp/package.json miniapp/package-lock.json ./
RUN npm ci
COPY miniapp/ ./
RUN npm run build:h5

FROM nginx:1.27-alpine
COPY miniapp/nginx.prod.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
