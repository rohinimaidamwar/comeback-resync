FROM python:3.12-slim
RUN useradd -m app
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p db && chown -R app /srv
USER app
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","1"]
