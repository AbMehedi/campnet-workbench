# Development image: runs the Vite dev server. A production build/serve stage comes with Milestone 6.
FROM node:24-slim
WORKDIR /srv/frontend
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
