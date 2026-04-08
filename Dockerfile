# Usamos una imagen ligera de Python
FROM python:3.9-slim

# Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiamos los requisitos primero (para aprovechar la caché de Docker)
COPY requirements.txt .

# Instalamos las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código
COPY . .

# Exponemos el puerto (Render usa el puerto que le asigne el sistema, pero localmente es el 8000)
EXPOSE 8000

# El comando para arrancar la app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

