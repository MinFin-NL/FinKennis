# Stap 1: de Vue-app bouwen
FROM node:22-alpine AS build

WORKDIR /app

# npm 10 struikelt over de peer-dependencies van @nldd/design-system.
RUN npm install -g npm@11

COPY package.json package-lock.json ./
RUN npm ci

# Vite bakt de VITE_*-variabelen bij het bouwen in de bundel. De pipeline geeft de
# Keycloak-URL mee; zonder build-args draait de app zonder login (lokaal).
ARG VITE_AUTH_MODE=none
ARG VITE_OIDC_AUTHORITY=
ARG VITE_OIDC_CLIENT_ID=finkennis-frontend
ENV VITE_AUTH_MODE=$VITE_AUTH_MODE \
    VITE_OIDC_AUTHORITY=$VITE_OIDC_AUTHORITY \
    VITE_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID

COPY . .
RUN npm run build

# Stap 2: serveren met nginx
FROM nginx:alpine AS serve

# De entrypoint van nginx:alpine draait envsubst over templates/ (BACKEND_URL).
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
