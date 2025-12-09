# Dockerfile
FROM python:3.12-slim

# Imposta la directory di lavoro
WORKDIR /app

# Copia i file nella directory di lavoro
COPY . /app

# Imposta le variabili d'ambiente
ENV PYTHONDONTWRITEBYTECODE=1

# Imposta Python in modalità non bufferizzata
ENV PYTHONUNBUFFERED=1

# Installa le dipendenze di sistema e Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Installa le dipendenze Python    
RUN pip install --no-cache-dir -r requirements.txt

# Comando di default per eseguire l'applicazione
CMD ["python", "app.py"]