# Imagen para cualquier hosting que corra contenedores (Render, Railway, Fly, Koyeb).
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements-nube.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-nube.txt

COPY . .

# El front ya viene compilado en web/dist, así que no hace falta Node acá.
ENV PORT=8000 HILO_SEMBRAR=1
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
