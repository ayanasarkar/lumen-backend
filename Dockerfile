FROM golang:1.22-bookworm
RUN apt-get update && apt-get install -y python3 python3-pip
WORKDIR /app
COPY . .
CMD ["sleep", "infinity"]
