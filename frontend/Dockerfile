FROM node:20-alpine AS build

WORKDIR /workspace/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
COPY specs/ /workspace/specs/
RUN npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.prod.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/frontend/dist /usr/share/nginx/html

EXPOSE 80
