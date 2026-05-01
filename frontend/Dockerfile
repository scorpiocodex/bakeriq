FROM node:20-alpine

ARG UID=1000
ARG GID=1000

RUN deluser --remove-home node 2>/dev/null || true; \
    addgroup -g ${GID} app && \
    adduser -D -u ${UID} -G app -s /bin/sh app

WORKDIR /app
RUN chown -R app:app /app

# Switch to app user BEFORE installing dependencies
USER app

COPY --chown=app:app package*.json ./
RUN npm install

COPY --chown=app:app . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]